import numpy as np, pandas as pd, os

# Random generator & size
rng = np.random.default_rng(42)
N = 600  # number of patients

# Demographics
races = ['White','Black','Hispanic','Asian','Other']
sexes = ['F','M']
df = pd.DataFrame({
    'patient_id': np.arange(1, N+1),
    'race': rng.choice(races, size=N, p=[0.45,0.20,0.20,0.10,0.05]),
    'ethnicity': rng.choice(['Hispanic/Latino','Not Hispanic/Latino'], size=N, p=[0.25,0.75]),
    'sex': rng.choice(sexes, size=N, p=[0.52,0.48]),
    'age': rng.integers(20, 90, size=N),
})

# Eligibility probability (mock ground truth)
base_elig = 0.30 + 0.001*(df['age']-50)
base_elig += df['race'].map({'Black':0.02,'Hispanic':0.01,'Asian':-0.01}).fillna(0)
prob_elig = np.clip(base_elig, 0.05, 0.8)
df['eligible'] = (rng.random(N) < prob_elig).astype(int)

# Simulate biased selection (over-select White, under-select Black/Hispanic)
bias = df['race'].map({'White':+0.05,'Black':-0.05,'Hispanic':-0.03}).fillna(0)
score = 0.6*df['eligible'] + 0.4*rng.random(N) + bias
prob_sel = np.clip(score, 0, 1)
df['selected'] = (rng.random(N) < prob_sel).astype(int)

# Save
os.makedirs('data', exist_ok=True)
out = 'data/mock_recruitment.csv'
df.to_csv(out, index=False)
print(f'✅ Wrote {out} with {len(df)} rows')
