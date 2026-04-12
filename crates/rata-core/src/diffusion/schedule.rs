use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffusionSchedule {
    pub betas: Vec<f64>,
    pub alphas: Vec<f64>,
    pub alpha_bars: Vec<f64>,
}

impl DiffusionSchedule {
    pub fn linear(timesteps: usize, beta_start: f64, beta_end: f64) -> Self {
        let mut betas = Vec::with_capacity(timesteps);
        let mut alphas = Vec::with_capacity(timesteps);
        let mut alpha_bars = Vec::with_capacity(timesteps);
        let mut running = 1.0;

        for step in 0..timesteps {
            let ratio = if timesteps <= 1 {
                0.0
            } else {
                step as f64 / (timesteps - 1) as f64
            };
            let beta = beta_start + ratio * (beta_end - beta_start);
            let alpha = 1.0 - beta;
            running *= alpha;
            betas.push(beta);
            alphas.push(alpha);
            alpha_bars.push(running);
        }

        Self {
            betas,
            alphas,
            alpha_bars,
        }
    }
}
