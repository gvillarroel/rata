param(
    [string]$OutputMarkdown = "docs/synthetic-evaluation-results.md",
    [string]$WorkDir = "datasets/converted/evaluation",
    [int]$SeedTrain = 42,
    [int]$SeedGenerate = 7,
    [double]$DpEpsilon = 1.0
)

$ErrorActionPreference = "Stop"

function Get-Json {
    param([string]$Path)
    Get-Content $Path -Raw | ConvertFrom-Json
}

function Invoke-RataJson {
    param(
        [string]$Command,
        [string]$OutputPath
    )
    Invoke-Expression $Command | Set-Content $OutputPath
    Get-Json $OutputPath
}

function Get-ColumnStats {
    param($Stats, [string]$Name)
    $Stats.columns | Where-Object { $_.name -eq $Name } | Select-Object -First 1
}

function Get-PairStats {
    param($Stats, [string]$Left, [string]$Right)
    $Stats.column_pairs | Where-Object { $_.left -eq $Left -and $_.right -eq $Right } | Select-Object -First 1
}

function Get-NumericColumns {
    param($Stats)
    @(
        $Stats.columns |
            Where-Object { $_.numeric_summary -ne $null } |
            ForEach-Object { $_.name }
    )
}

function Get-CorrelationSummary {
    param($OriginalStats, $CandidateStats)

    $pairMap = @{}
    foreach ($pair in $OriginalStats.column_pairs) {
        if ($pair.numeric_relationship -ne $null) {
            $pairMap["$($pair.left)|$($pair.right)"] = $pair
        }
    }

    $deltas = @()
    foreach ($pair in $CandidateStats.column_pairs) {
        if ($pair.numeric_relationship -eq $null) {
            continue
        }
        $key = "$($pair.left)|$($pair.right)"
        if (-not $pairMap.ContainsKey($key)) {
            continue
        }
        $originalPair = $pairMap[$key]
        $delta = [math]::Abs($pair.numeric_relationship.pearson_correlation - $originalPair.numeric_relationship.pearson_correlation)
        $deltas += [pscustomobject]@{
            Pair = "$($pair.left)/$($pair.right)"
            Delta = $delta
            Original = $originalPair.numeric_relationship.pearson_correlation
            Candidate = $pair.numeric_relationship.pearson_correlation
        }
    }

    if ($deltas.Count -eq 0) {
        return [pscustomobject]@{
            PairCount = 0
            MeanAbsPearsonDelta = $null
            MaxAbsPearsonDelta = $null
            TopPairs = @()
        }
    }

    $topPairs = $deltas | Sort-Object Delta -Descending | Select-Object -First 3
    [pscustomobject]@{
        PairCount = $deltas.Count
        MeanAbsPearsonDelta = (($deltas | Measure-Object -Property Delta -Average).Average)
        MaxAbsPearsonDelta = (($deltas | Measure-Object -Property Delta -Maximum).Maximum)
        TopPairs = @($topPairs)
    }
}

function Get-CanonicalRowSignature {
    param($Row, [string[]]$Columns)
    ($Columns | Sort-Object | ForEach-Object {
        $name = $_
        $value = $Row.$name
        "$name=$($value | ConvertTo-Json -Compress)"
    }) -join "|"
}

function Get-ExactReplayRatio {
    param($OriginalRows, $CandidateRows, [string[]]$Columns)

    $originalSet = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($row in $OriginalRows) {
        [void]$originalSet.Add((Get-CanonicalRowSignature -Row $row -Columns $Columns))
    }

    $matches = 0
    foreach ($row in $CandidateRows) {
        if ($originalSet.Contains((Get-CanonicalRowSignature -Row $row -Columns $Columns))) {
            $matches += 1
        }
    }

    if ($CandidateRows.Count -eq 0) {
        return 0.0
    }

    return ($matches / $CandidateRows.Count)
}

function Get-StandardizedRows {
    param($Rows, [string[]]$NumericColumns, $Scale)

    if ($null -eq $Scale) {
        $Scale = Get-StandardizationScale -Rows $Rows -NumericColumns $NumericColumns
    }

    $means = $Scale.Means
    $stddevs = $Scale.Stddevs

    @(
        $Rows | ForEach-Object {
            $vector = @()
            foreach ($column in $NumericColumns) {
                $vector += (([double]($_.$column) - $means[$column]) / $stddevs[$column])
            }
            ,$vector
        }
    )
}

function Get-StandardizationScale {
    param($Rows, [string[]]$NumericColumns)

    $means = @{}
    $stddevs = @{}
    foreach ($column in $NumericColumns) {
        $values = @($Rows | ForEach-Object { [double]($_.$column) })
        $mean = ($values | Measure-Object -Average).Average
        $variance = 0.0
        foreach ($value in $values) {
            $delta = $value - $mean
            $variance += $delta * $delta
        }
        $stddev = [math]::Sqrt($variance / [math]::Max($values.Count, 1))
        if ($stddev -eq 0.0) { $stddev = 1.0 }
        $means[$column] = $mean
        $stddevs[$column] = $stddev
    }

    [pscustomobject]@{
        Means = $means
        Stddevs = $stddevs
    }
}

function Get-Distance {
    param([double[]]$Left, [double[]]$Right)
    $sum = 0.0
    for ($i = 0; $i -lt $Left.Count; $i++) {
        $delta = $Left[$i] - $Right[$i]
        $sum += $delta * $delta
    }
    [math]::Sqrt($sum)
}

function Get-DcrSummary {
    param($OriginalRows, $CandidateRows, [string[]]$NumericColumns)

    if ($NumericColumns.Count -eq 0 -or $CandidateRows.Count -eq 0) {
        return [pscustomobject]@{
            Median = $null
            P5 = $null
            Mean = $null
        }
    }

    $scale = Get-StandardizationScale -Rows $OriginalRows -NumericColumns $NumericColumns
    $standardOriginal = Get-StandardizedRows -Rows $OriginalRows -NumericColumns $NumericColumns -Scale $scale
    $standardCandidate = Get-StandardizedRows -Rows $CandidateRows -NumericColumns $NumericColumns -Scale $scale
    $distances = @()

    foreach ($candidate in $standardCandidate) {
        $best = [double]::PositiveInfinity
        foreach ($original in $standardOriginal) {
            $distance = Get-Distance -Left $candidate -Right $original
            if ($distance -lt $best) {
                $best = $distance
            }
        }
        $distances += $best
    }

    $sorted = @($distances | Sort-Object)
    $count = $sorted.Count
    $median = if ($count % 2 -eq 1) { $sorted[[int]($count / 2)] } else { ($sorted[$count / 2 - 1] + $sorted[$count / 2]) / 2.0 }
    $p5Index = [math]::Floor(([math]::Max($count - 1, 0)) * 0.05)
    [pscustomobject]@{
        Median = $median
        P5 = $sorted[$p5Index]
        Mean = (($sorted | Measure-Object -Average).Average)
    }
}

function Get-TargetColumns {
    param($Stats)
    @(
        $Stats.columns |
            Where-Object { $_.dominant_type -eq "string" -or $_.dominant_type -eq "boolean" } |
            Where-Object { $_.distinct_count -ge 2 -and $_.distinct_count -le 20 } |
            Sort-Object distinct_count |
            ForEach-Object { $_.name }
    )
}

function Format-Number {
    param($Value)
    if ($null -eq $Value) { return "n/a" }
    [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:N4}", [double]$Value)
}

function Format-PrivacySummary {
    param($Method)
    if ($null -eq $Method) { return "n/a" }

    "DCR median " + (Format-Number $Method.DcrMedian) +
        ", replay " + (Format-Number $Method.ExactReplayRatio) +
        ", numeric replay " + (Format-Number $Method.ExactNumericReplayRatio) +
        ", non-numeric replay " + (Format-Number $Method.ExactNonNumericReplayRatio)
}

function Format-CorrelationSummary {
    param($Method)
    if ($null -eq $Method) { return "n/a" }

    "mean " + (Format-Number $Method.MeanAbsPearsonDelta) +
        ", max " + (Format-Number $Method.MaxAbsPearsonDelta)
}

function Get-CorePrivacySummary {
    param($Evaluation)

    if ($null -eq $Evaluation -or $null -eq $Evaluation.privacy) {
        return $null
    }

    $privacy = $Evaluation.privacy
    [pscustomobject]@{
        DcrMedian = $privacy.distance_to_closest_record.median
        DcrP5 = $privacy.distance_to_closest_record.p5
        ExactReplayRatio = $privacy.exact_row_match_ratio
        ExactNumericReplayRatio = $privacy.exact_numeric_signature_match_ratio
        ExactNonNumericReplayRatio = $privacy.exact_non_numeric_signature_match_ratio
        RareValueColumns = $privacy.rare_value_alerts.columns_with_alerts
        RareNumericValueColumns = $privacy.rare_numeric_value_alerts.columns_with_alerts
    }
}

function Get-EvaluationSummary {
    param(
        [string]$DatasetPath,
        [string]$DatasetName,
        [string]$TargetColumn,
        [string]$MinorityLabel,
        [string]$WorkRoot
    )

    $safeName = $DatasetName -replace "[^a-zA-Z0-9\-]+", "-"
    $originalStatsPath = Join-Path $WorkRoot "$safeName.original.stats.json"
    $originalStats = Invoke-RataJson -Command "rata stats `"$DatasetPath`" --output json" -OutputPath $originalStatsPath
    $originalHeadPath = Join-Path $WorkRoot "$safeName.original.head.json"
    $originalHead = Invoke-RataJson -Command "rata head `"$DatasetPath`" --rows $($originalStats.row_count) --output json" -OutputPath $originalHeadPath
    $originalRows = @($originalHead.rows)
    $numericColumns = Get-NumericColumns -Stats $originalStats

    $summary = [ordered]@{
        Dataset = $DatasetName
        Source = $DatasetPath
        OriginalRows = $originalStats.row_count
        TargetColumn = $TargetColumn
        NumericColumns = ($numericColumns -join ", ")
        Diffusion = $null
        Smote = $null
        DpNoise = $null
        Notes = @()
    }

    if ($numericColumns.Count -gt 0) {
        $modelPath = Join-Path $WorkRoot "$safeName.df.json"
        $diffTrainPath = Join-Path $WorkRoot "$safeName.diffusion-train.report.json"
        $diffDataPath = Join-Path $WorkRoot "$safeName.diffusion.json"
        $diffGenPath = Join-Path $WorkRoot "$safeName.diffusion-generate.report.json"
        $diffStatsPath = Join-Path $WorkRoot "$safeName.diffusion.stats.json"
        $diffHeadPath = Join-Path $WorkRoot "$safeName.diffusion.head.json"

        $diffTrain = Invoke-RataJson -Command "rata train df `"$DatasetPath`" `"$modelPath`" --seed $SeedTrain" -OutputPath $diffTrainPath
        $diffGen = Invoke-RataJson -Command "rata gen df `"$modelPath`" `"$DatasetPath`" `"$diffDataPath`" --rows $($originalStats.row_count) --seed $SeedGenerate" -OutputPath $diffGenPath
        $diffStats = Invoke-RataJson -Command "rata stats `"$diffDataPath`" --output json" -OutputPath $diffStatsPath
        $diffHead = Invoke-RataJson -Command "rata head `"$diffDataPath`" --rows $($originalStats.row_count) --output json" -OutputPath $diffHeadPath
        $diffRows = @($diffHead.rows)

        $diffCorr = Get-CorrelationSummary -OriginalStats $originalStats -CandidateStats $diffStats
        $diffPrivacy = Get-DcrSummary -OriginalRows $originalRows -CandidateRows $diffRows -NumericColumns $numericColumns
        $diffExact = Get-ExactReplayRatio -OriginalRows $originalRows -CandidateRows $diffRows -Columns @($originalHead.columns)
        $diffExactNumeric = Get-ExactReplayRatio -OriginalRows $originalRows -CandidateRows $diffRows -Columns $numericColumns
        $diffCorePrivacy = Get-CorePrivacySummary -Evaluation $diffGen.evaluation

        $summary.Diffusion = [ordered]@{
            Rows = $diffStats.row_count
            TrainingMse = $diffTrain.training_mse
            MeanAbsPearsonDelta = $diffCorr.MeanAbsPearsonDelta
            MaxAbsPearsonDelta = $diffCorr.MaxAbsPearsonDelta
            DcrMedian = if ($diffCorePrivacy) { $diffCorePrivacy.DcrMedian } else { $diffPrivacy.Median }
            DcrP5 = if ($diffCorePrivacy) { $diffCorePrivacy.DcrP5 } else { $diffPrivacy.P5 }
            ExactReplayRatio = if ($diffCorePrivacy) { $diffCorePrivacy.ExactReplayRatio } else { $diffExact }
            ExactNumericReplayRatio = if ($diffCorePrivacy) { $diffCorePrivacy.ExactNumericReplayRatio } else { $diffExactNumeric }
            ExactNonNumericReplayRatio = if ($diffCorePrivacy) { $diffCorePrivacy.ExactNonNumericReplayRatio } else { $null }
            RareValueColumns = if ($diffCorePrivacy) { $diffCorePrivacy.RareValueColumns } else { $null }
            RareNumericValueColumns = if ($diffCorePrivacy) { $diffCorePrivacy.RareNumericValueColumns } else { $null }
            TopPairs = @($diffCorr.TopPairs)
        }

        $dpPath = Join-Path $WorkRoot "$safeName.dp-noise.json"
        $dpReportPath = Join-Path $WorkRoot "$safeName.dp-noise.report.json"
        $dpStatsPath = Join-Path $WorkRoot "$safeName.dp-noise.stats.json"

        $dpReport = Invoke-RataJson -Command "rata synth dp-noise `"$DatasetPath`" `"$dpPath`" --epsilon $DpEpsilon --seed $SeedTrain" -OutputPath $dpReportPath
        $dpStats = Invoke-RataJson -Command "rata stats `"$dpPath`" --output json" -OutputPath $dpStatsPath

        $dpCorr = Get-CorrelationSummary -OriginalStats $originalStats -CandidateStats $dpStats
        $dpCorePrivacy = Get-CorePrivacySummary -Evaluation $dpReport.evaluation

        $summary.DpNoise = [ordered]@{
            Rows = $dpStats.row_count
            Epsilon = $DpEpsilon
            MeanAbsPearsonDelta = $dpCorr.MeanAbsPearsonDelta
            MaxAbsPearsonDelta = $dpCorr.MaxAbsPearsonDelta
            DcrMedian = if ($dpCorePrivacy) { $dpCorePrivacy.DcrMedian } else { $null }
            DcrP5 = if ($dpCorePrivacy) { $dpCorePrivacy.DcrP5 } else { $null }
            ExactReplayRatio = if ($dpCorePrivacy) { $dpCorePrivacy.ExactReplayRatio } else { $null }
            ExactNumericReplayRatio = if ($dpCorePrivacy) { $dpCorePrivacy.ExactNumericReplayRatio } else { $null }
            ExactNonNumericReplayRatio = if ($dpCorePrivacy) { $dpCorePrivacy.ExactNonNumericReplayRatio } else { $null }
            RareValueColumns = if ($dpCorePrivacy) { $dpCorePrivacy.RareValueColumns } else { $null }
            RareNumericValueColumns = if ($dpCorePrivacy) { $dpCorePrivacy.RareNumericValueColumns } else { $null }
            TopPairs = @($dpCorr.TopPairs)
        }
    } else {
        $summary.Notes += "Diffusion not evaluated: dataset has no fully numeric columns."
        $summary.Notes += "DP noise not evaluated: dataset has no fully numeric columns."
    }

    if ($TargetColumn) {
        $smotePath = Join-Path $WorkRoot "$safeName.smote.json"
        $smoteReportPath = Join-Path $WorkRoot "$safeName.smote.report.json"
        $smoteStatsPath = Join-Path $WorkRoot "$safeName.smote.stats.json"
        $smoteHeadPath = Join-Path $WorkRoot "$safeName.smote.head.json"

        $minorityFlag = if ($MinorityLabel) { " --minority-label `"$MinorityLabel`"" } else { "" }
        $smoteReport = Invoke-RataJson -Command "rata synth smote `"$DatasetPath`" `"$smotePath`" --target $TargetColumn$minorityFlag --seed $SeedTrain --target-rows $($originalStats.row_count)" -OutputPath $smoteReportPath
        $smoteStats = Invoke-RataJson -Command "rata stats `"$smotePath`" --output json" -OutputPath $smoteStatsPath
        $smoteHead = Invoke-RataJson -Command "rata head `"$smotePath`" --rows $($originalStats.row_count) --output json" -OutputPath $smoteHeadPath
        $smoteRows = @($smoteHead.rows)

        $smoteCorr = Get-CorrelationSummary -OriginalStats $originalStats -CandidateStats $smoteStats
        $smotePrivacy = Get-DcrSummary -OriginalRows $originalRows -CandidateRows $smoteRows -NumericColumns $numericColumns
        $smoteExact = Get-ExactReplayRatio -OriginalRows $originalRows -CandidateRows $smoteRows -Columns @($originalHead.columns)
        $smoteExactNumeric = Get-ExactReplayRatio -OriginalRows $originalRows -CandidateRows $smoteRows -Columns $numericColumns
        $smoteCorePrivacy = Get-CorePrivacySummary -Evaluation $smoteReport.final_output_evaluation

        $summary.Smote = [ordered]@{
            Rows = $smoteStats.row_count
            MinorityLabel = $smoteReport.minority_label
            MeanAbsPearsonDelta = $smoteCorr.MeanAbsPearsonDelta
            MaxAbsPearsonDelta = $smoteCorr.MaxAbsPearsonDelta
            DcrMedian = if ($smoteCorePrivacy) { $smoteCorePrivacy.DcrMedian } else { $smotePrivacy.Median }
            DcrP5 = if ($smoteCorePrivacy) { $smoteCorePrivacy.DcrP5 } else { $smotePrivacy.P5 }
            ExactReplayRatio = if ($smoteCorePrivacy) { $smoteCorePrivacy.ExactReplayRatio } else { $smoteExact }
            ExactNumericReplayRatio = if ($smoteCorePrivacy) { $smoteCorePrivacy.ExactNumericReplayRatio } else { $smoteExactNumeric }
            ExactNonNumericReplayRatio = if ($smoteCorePrivacy) { $smoteCorePrivacy.ExactNonNumericReplayRatio } else { $null }
            RareValueColumns = if ($smoteCorePrivacy) { $smoteCorePrivacy.RareValueColumns } else { $null }
            RareNumericValueColumns = if ($smoteCorePrivacy) { $smoteCorePrivacy.RareNumericValueColumns } else { $null }
            TopPairs = @($smoteCorr.TopPairs)
        }
    } else {
        $summary.Notes += "SMOTE not evaluated: no suitable low-cardinality label column."
    }

    [pscustomobject]$summary
}

function Write-MarkdownReport {
    param(
        [object[]]$Summaries,
        [string]$OutputPath
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Synthetic Generator Evaluation")
    $lines.Add("")
    $lines.Add("This document compares the Rust diffusion path, SMOTE, and DP noise on the local test datasets.")
    $lines.Add("")
    $lines.Add("Priority order used in this evaluation:")
    $lines.Add("")
    $lines.Add("- privacy first")
    $lines.Add("- correlation preservation second")
    $lines.Add("- simple distribution summaries third")
    $lines.Add("")
    $lines.Add("Metrics used:")
    $lines.Add("")
    $lines.Add("- DCR median and DCR p5: nearest-neighbor distance from synthetic rows to original rows over common numeric columns")
    $lines.Add("- exact replay ratio: exact full-row matches against the original dataset")
    $lines.Add("- exact numeric replay ratio: exact matches on numeric columns only")
    $lines.Add("- exact non-numeric replay ratio: exact matches on common non-numeric scalar signatures")
    $lines.Add("- mean abs Pearson delta: average absolute Pearson correlation drift over numeric column pairs")
    $lines.Add("- max abs Pearson delta: largest Pearson correlation drift over numeric column pairs")
    $lines.Add("")
    $lines.Add("| Dataset | Rows | Target | Diffusion Privacy | Diffusion Corr | SMOTE Privacy | SMOTE Corr | DP Noise Privacy | DP Noise Corr | Notes |")
    $lines.Add("| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |")

    foreach ($summary in $Summaries) {
        $diffPrivacy = Format-PrivacySummary -Method $summary.Diffusion
        $diffCorr = Format-CorrelationSummary -Method $summary.Diffusion
        $smotePrivacy = Format-PrivacySummary -Method $summary.Smote
        $smoteCorr = Format-CorrelationSummary -Method $summary.Smote
        $dpPrivacy = Format-PrivacySummary -Method $summary.DpNoise
        $dpCorr = Format-CorrelationSummary -Method $summary.DpNoise
        $notes = if ($summary.Notes.Count -gt 0) { ($summary.Notes -join " ") } else { "" }
        $lines.Add("| $($summary.Dataset) | $($summary.OriginalRows) | $($summary.TargetColumn) | $diffPrivacy | $diffCorr | $smotePrivacy | $smoteCorr | $dpPrivacy | $dpCorr | $notes |")
    }

    foreach ($summary in $Summaries) {
        $lines.Add("")
        $lines.Add("## $($summary.Dataset)")
        $lines.Add("")
        $lines.Add("- Source: ``$($summary.Source)``")
        $lines.Add("- Original rows: ``$($summary.OriginalRows)``")
        $lines.Add("- Target column: ``$($summary.TargetColumn)``")
        $lines.Add("- Numeric columns: ``$($summary.NumericColumns)``")
        if ($summary.Notes.Count -gt 0) {
            foreach ($note in $summary.Notes) {
                $lines.Add("- Note: $note")
            }
        }

        if ($summary.Diffusion) {
            $lines.Add("")
            $lines.Add("### Diffusion")
            $lines.Add("")
            $lines.Add("- Training MSE: ``$(Format-Number $summary.Diffusion.TrainingMse)``")
            $lines.Add("- DCR median: ``$(Format-Number $summary.Diffusion.DcrMedian)``")
            $lines.Add("- DCR p5: ``$(Format-Number $summary.Diffusion.DcrP5)``")
            $lines.Add("- Exact replay ratio: ``$(Format-Number $summary.Diffusion.ExactReplayRatio)``")
            $lines.Add("- Exact numeric replay ratio: ``$(Format-Number $summary.Diffusion.ExactNumericReplayRatio)``")
            $lines.Add("- Exact non-numeric replay ratio: ``$(Format-Number $summary.Diffusion.ExactNonNumericReplayRatio)``")
            $lines.Add("- Rare non-numeric value columns: ``$($summary.Diffusion.RareValueColumns)``")
            $lines.Add("- Rare numeric value columns: ``$($summary.Diffusion.RareNumericValueColumns)``")
            $lines.Add("- Mean absolute Pearson delta: ``$(Format-Number $summary.Diffusion.MeanAbsPearsonDelta)``")
            $lines.Add("- Max absolute Pearson delta: ``$(Format-Number $summary.Diffusion.MaxAbsPearsonDelta)``")
            if ($summary.Diffusion.TopPairs.Count -gt 0) {
                $lines.Add("- Top drift pairs:")
                foreach ($pair in $summary.Diffusion.TopPairs) {
                    $lines.Add("  - ``$($pair.Pair)`` delta ``$(Format-Number $pair.Delta)``")
                }
            }
        }

        if ($summary.Smote) {
            $lines.Add("")
            $lines.Add("### SMOTE")
            $lines.Add("")
            $lines.Add("- Minority label: ``$($summary.Smote.MinorityLabel)``")
            $lines.Add("- DCR median: ``$(Format-Number $summary.Smote.DcrMedian)``")
            $lines.Add("- DCR p5: ``$(Format-Number $summary.Smote.DcrP5)``")
            $lines.Add("- Exact replay ratio: ``$(Format-Number $summary.Smote.ExactReplayRatio)``")
            $lines.Add("- Exact numeric replay ratio: ``$(Format-Number $summary.Smote.ExactNumericReplayRatio)``")
            $lines.Add("- Exact non-numeric replay ratio: ``$(Format-Number $summary.Smote.ExactNonNumericReplayRatio)``")
            $lines.Add("- Rare non-numeric value columns: ``$($summary.Smote.RareValueColumns)``")
            $lines.Add("- Rare numeric value columns: ``$($summary.Smote.RareNumericValueColumns)``")
            $lines.Add("- Mean absolute Pearson delta: ``$(Format-Number $summary.Smote.MeanAbsPearsonDelta)``")
            $lines.Add("- Max absolute Pearson delta: ``$(Format-Number $summary.Smote.MaxAbsPearsonDelta)``")
            if ($summary.Smote.TopPairs.Count -gt 0) {
                $lines.Add("- Top drift pairs:")
                foreach ($pair in $summary.Smote.TopPairs) {
                    $lines.Add("  - ``$($pair.Pair)`` delta ``$(Format-Number $pair.Delta)``")
                }
            }
        }

        if ($summary.DpNoise) {
            $lines.Add("")
            $lines.Add("### DP Noise")
            $lines.Add("")
            $lines.Add("- Epsilon: ``$(Format-Number $summary.DpNoise.Epsilon)``")
            $lines.Add("- DCR median: ``$(Format-Number $summary.DpNoise.DcrMedian)``")
            $lines.Add("- DCR p5: ``$(Format-Number $summary.DpNoise.DcrP5)``")
            $lines.Add("- Exact replay ratio: ``$(Format-Number $summary.DpNoise.ExactReplayRatio)``")
            $lines.Add("- Exact numeric replay ratio: ``$(Format-Number $summary.DpNoise.ExactNumericReplayRatio)``")
            $lines.Add("- Exact non-numeric replay ratio: ``$(Format-Number $summary.DpNoise.ExactNonNumericReplayRatio)``")
            $lines.Add("- Rare non-numeric value columns: ``$($summary.DpNoise.RareValueColumns)``")
            $lines.Add("- Rare numeric value columns: ``$($summary.DpNoise.RareNumericValueColumns)``")
            $lines.Add("- Mean absolute Pearson delta: ``$(Format-Number $summary.DpNoise.MeanAbsPearsonDelta)``")
            $lines.Add("- Max absolute Pearson delta: ``$(Format-Number $summary.DpNoise.MaxAbsPearsonDelta)``")
            if ($summary.DpNoise.TopPairs.Count -gt 0) {
                $lines.Add("- Top drift pairs:")
                foreach ($pair in $summary.DpNoise.TopPairs) {
                    $lines.Add("  - ``$($pair.Pair)`` delta ``$(Format-Number $pair.Delta)``")
                }
            }
        }
    }

    $parent = Split-Path $OutputPath -Parent
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    [System.IO.File]::WriteAllText(
        [System.IO.Path]::GetFullPath($OutputPath),
        (($lines -join "`n") + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
}

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$datasets = @(
    [pscustomobject]@{ Name = "iris.csv"; Path = "datasets/iris.csv"; Target = "species"; Minority = "setosa" },
    [pscustomobject]@{ Name = "cars.json"; Path = "datasets/cars.json"; Target = "Origin"; Minority = "Europe" },
    [pscustomobject]@{ Name = "news_headlines.jsonl"; Path = "datasets/news_headlines.jsonl"; Target = $null; Minority = $null },
    [pscustomobject]@{ Name = "userdata1.avro"; Path = "datasets/userdata1.avro"; Target = "gender"; Minority = "Male" },
    [pscustomobject]@{ Name = "userdata1.parquet"; Path = "datasets/userdata1.parquet"; Target = "gender"; Minority = "Male" }
)

$summaries = foreach ($dataset in $datasets) {
    Get-EvaluationSummary -DatasetPath $dataset.Path -DatasetName $dataset.Name -TargetColumn $dataset.Target -MinorityLabel $dataset.Minority -WorkRoot $WorkDir
}

Write-MarkdownReport -Summaries $summaries -OutputPath $OutputMarkdown
$jsonText = (($summaries | ConvertTo-Json -Depth 8) -replace "`r`n", "`n") -replace "`r", "`n"
[System.IO.File]::WriteAllText(
    [System.IO.Path]::GetFullPath([System.IO.Path]::ChangeExtension($OutputMarkdown, ".json")),
    ($jsonText + "`n"),
    [System.Text.UTF8Encoding]::new($false)
)
