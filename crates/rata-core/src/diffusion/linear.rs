use anyhow::{Result, anyhow};
use nalgebra::{DMatrix, DVector};

pub fn fit_ridge_multi_target(
    x_train: &DMatrix<f64>,
    y_train: &DMatrix<f64>,
    ridge_alpha: f64,
) -> Result<DMatrix<f64>> {
    let xt = x_train.transpose();
    let gram = &xt * x_train;
    let regularized =
        gram + DMatrix::<f64>::identity(x_train.ncols(), x_train.ncols()).scale(ridge_alpha);
    let rhs = xt * y_train;
    regularized
        .lu()
        .solve(&rhs)
        .ok_or_else(|| anyhow!("ridge system is singular"))
}

pub fn predict_row(weights: &DMatrix<f64>, input: &DVector<f64>) -> DVector<f64> {
    weights.transpose() * input
}
