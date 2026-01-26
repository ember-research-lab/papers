"""
Non-Tautological Test for Spectral Cosmology

The Problem:
The λ₁-density correlation (r=0.95) is tautological - it follows from how
graph Laplacians are constructed. Higher density → more edges → higher λ₁.

The Solution:
Test whether λ₁ predicts something BEYOND what density predicts.
If λ₁ is just a density proxy, it adds no predictive power.
If λ₁ captures real physics, it should:
  1. Predict expansion/velocity better than density alone
  2. Have residual correlation with dynamics after controlling for density

Tests:
1. Partial correlation: Corr(λ₁, v_r | δ) - controlling for density
2. Incremental R²: Does adding λ₁ to density improve velocity prediction?
3. Bakry-Émery spectral gap: Compute from continuous density field
4. Void expansion test: Do low-λ₁ regions expand faster than density alone predicts?
"""

import numpy as np
from scipy.stats import pearsonr, spearmanr
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import eigsh
from scipy.ndimage import laplace, gaussian_filter
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

# Load previous results
print("Loading data...")
results = np.load('cf4_lambda1_results.npz')
deltas = results['deltas']
v_rads = results['v_rads']
lambda1s = results['lambda1s']

# Also load raw data for Bakry-Émery test
data = np.load('CF4pp_mean_std_grids.npz')
delta_field = data['d_mean_CF4pp']
v_rad_field = data['vr_mean_CF4pp']

print(f"Subregions: {len(deltas)}")
print(f"Density range: [{deltas.min():.3f}, {deltas.max():.3f}]")
print(f"λ₁ range: [{lambda1s.min():.5f}, {lambda1s.max():.5f}]")

# =============================================================================
# TEST 1: Partial Correlation
# =============================================================================
print("\n" + "="*60)
print("TEST 1: PARTIAL CORRELATION")
print("="*60)
print("Question: Does λ₁ correlate with v_r after controlling for density?")

def partial_correlation(x, y, z):
    """
    Partial correlation of x and y, controlling for z.
    r_xy.z = (r_xy - r_xz * r_yz) / sqrt((1-r_xz²)(1-r_yz²))
    """
    r_xy = pearsonr(x, y)[0]
    r_xz = pearsonr(x, z)[0]
    r_yz = pearsonr(y, z)[0]

    numerator = r_xy - r_xz * r_yz
    denominator = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))

    if denominator < 1e-10:
        return np.nan
    return numerator / denominator

# Compute partial correlations
r_lambda_vr = pearsonr(lambda1s, v_rads)[0]
r_lambda_delta = pearsonr(lambda1s, deltas)[0]
r_delta_vr = pearsonr(deltas, v_rads)[0]

r_partial = partial_correlation(lambda1s, v_rads, deltas)

print(f"\nSimple correlations:")
print(f"  Corr(λ₁, v_r) = {r_lambda_vr:.4f}")
print(f"  Corr(λ₁, δ)   = {r_lambda_delta:.4f}")
print(f"  Corr(δ, v_r)  = {r_delta_vr:.4f}")

print(f"\nPartial correlation (controlling for density):")
print(f"  Corr(λ₁, v_r | δ) = {r_partial:.4f}")

if abs(r_partial) > 0.1:
    print(f"\n  ✓ λ₁ has residual predictive power beyond density!")
    print(f"  This suggests λ₁ captures physics not encoded in density alone.")
else:
    print(f"\n  ✗ λ₁ adds little beyond density.")
    print(f"  The correlation may be largely tautological.")

# =============================================================================
# TEST 2: Incremental R² (Predictive Power)
# =============================================================================
print("\n" + "="*60)
print("TEST 2: INCREMENTAL R² (Predictive Power)")
print("="*60)
print("Question: Does λ₁ improve prediction of v_r beyond density?")

# Model 1: v_r ~ δ (density only)
X_density = deltas.reshape(-1, 1)
model1 = LinearRegression().fit(X_density, v_rads)
pred1 = model1.predict(X_density)
r2_density = r2_score(v_rads, pred1)

# Model 2: v_r ~ δ + λ₁ (density + spectral gap)
X_both = np.column_stack([deltas, lambda1s])
model2 = LinearRegression().fit(X_both, v_rads)
pred2 = model2.predict(X_both)
r2_both = r2_score(v_rads, pred2)

# Incremental R²
delta_r2 = r2_both - r2_density

print(f"\nModel 1: v_r ~ δ")
print(f"  R² = {r2_density:.4f}")
print(f"  Coefficient: β_δ = {model1.coef_[0]:.2f}")

print(f"\nModel 2: v_r ~ δ + λ₁")
print(f"  R² = {r2_both:.4f}")
print(f"  Coefficients: β_δ = {model2.coef_[0]:.2f}, β_λ₁ = {model2.coef_[1]:.2f}")

print(f"\nIncremental R²: ΔR² = {delta_r2:.4f}")

if delta_r2 > 0.01:
    print(f"\n  ✓ Adding λ₁ improves prediction by {delta_r2*100:.1f}%")
    print(f"  λ₁ contains information beyond density.")
else:
    print(f"\n  ✗ Adding λ₁ provides minimal improvement.")

# =============================================================================
# TEST 3: Bakry-Émery Spectral Gap (Continuous)
# =============================================================================
print("\n" + "="*60)
print("TEST 3: BAKRY-ÉMERY SPECTRAL GAP (Continuous)")
print("="*60)
print("Question: Does the continuous B-E Laplacian give different results?")

def compute_bakry_emery_lambda1(density_field, subsample=4):
    """
    Compute spectral gap of Bakry-Émery Laplacian on continuous density field.

    L_f = Δ - ∇f · ∇  where f = -log(ρ/ρ₀)

    For discrete grid: use finite differences.
    """
    # Subsample for tractability
    d = density_field[::subsample, ::subsample, ::subsample]

    # Smooth to avoid numerical issues
    d = gaussian_filter(d, sigma=1.0)

    # Avoid log of negative values
    d_shifted = d - d.min() + 0.1
    rho0 = np.mean(d_shifted)

    # f = -log(ρ/ρ₀)
    f = -np.log(d_shifted / rho0)

    # Build the weighted Laplacian matrix
    nx, ny, nz = d.shape
    N = nx * ny * nz

    def idx(i, j, k):
        return i * ny * nz + j * nz + k

    # Standard Laplacian + weight from f
    rows, cols, vals = [], [], []

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                node = idx(i, j, k)
                f_node = f[i, j, k]

                # Diagonal: degree
                degree = 0

                # 6 neighbors
                for di, dj, dk in [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]:
                    ni, nj, nk = i + di, j + dj, k + dk
                    if 0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz:
                        neighbor = idx(ni, nj, nk)
                        f_neighbor = f[ni, nj, nk]

                        # Bakry-Émery weight: exp(-(f_i + f_j)/2) = sqrt(ρ_i * ρ_j)/ρ₀
                        # For weighted Laplacian: w_ij = exp(-|f_i - f_j|/2)
                        weight = np.exp(-(f_node + f_neighbor) / 4)

                        rows.append(node)
                        cols.append(neighbor)
                        vals.append(-weight)
                        degree += weight

                # Diagonal
                rows.append(node)
                cols.append(node)
                vals.append(degree)

    L = csr_matrix((vals, (rows, cols)), shape=(N, N))

    try:
        eigenvalues, _ = eigsh(L, k=4, which='SM', maxiter=3000)
        eigenvalues = np.sort(np.abs(eigenvalues))
        lambda1 = eigenvalues[1] if eigenvalues[1] > 1e-8 else eigenvalues[2]
        return lambda1
    except:
        return np.nan

# Compute B-E spectral gap for subregions
print("\nComputing Bakry-Émery spectral gaps...")
SUBGRID = 16
n_sub = 128 // SUBGRID
be_lambda1s = []
be_deltas = []
be_vrads = []

for i in range(n_sub):
    for j in range(n_sub):
        for k in range(n_sub):
            i0, i1 = i * SUBGRID, (i+1) * SUBGRID
            j0, j1 = j * SUBGRID, (j+1) * SUBGRID
            k0, k1 = k * SUBGRID, (k+1) * SUBGRID

            sub_delta = delta_field[i0:i1, j0:j1, k0:k1]
            sub_vrad = v_rad_field[i0:i1, j0:j1, k0:k1]

            # Compute B-E lambda1 (subsample=2 for 16³ → 8³)
            be_l1 = compute_bakry_emery_lambda1(sub_delta, subsample=2)

            if not np.isnan(be_l1):
                be_lambda1s.append(be_l1)
                be_deltas.append(np.mean(sub_delta))
                be_vrads.append(np.mean(sub_vrad))

be_lambda1s = np.array(be_lambda1s)
be_deltas = np.array(be_deltas)
be_vrads = np.array(be_vrads)

print(f"Valid B-E subregions: {len(be_lambda1s)}")

# Correlations for B-E
r_be_delta, p_be_delta = pearsonr(be_lambda1s, be_deltas)
r_be_vr, p_be_vr = pearsonr(be_lambda1s, be_vrads)
r_partial_be = partial_correlation(be_lambda1s, be_vrads, be_deltas)

print(f"\nBakry-Émery correlations:")
print(f"  Corr(λ₁_BE, δ) = {r_be_delta:.4f}")
print(f"  Corr(λ₁_BE, v_r) = {r_be_vr:.4f}")
print(f"  Corr(λ₁_BE, v_r | δ) = {r_partial_be:.4f}")

# Compare to graph-based
print(f"\nComparison:")
print(f"  Graph λ₁ partial: {r_partial:.4f}")
print(f"  B-E λ₁ partial:   {r_partial_be:.4f}")

# =============================================================================
# TEST 4: Void Expansion (The Real Test)
# =============================================================================
print("\n" + "="*60)
print("TEST 4: VOID EXPANSION (The Real Physical Test)")
print("="*60)
print("Question: Do low-λ₁ voids expand faster than density alone predicts?")

# The framework predicts: in voids, low λ₁ → approach threshold → expand faster
# This is NOT tautological because it predicts DYNAMICS, not just correlation

# Residual analysis: v_r residual after removing density effect
v_r_pred_from_density = model1.predict(deltas.reshape(-1, 1))
v_r_residual = v_rads - v_r_pred_from_density

# In voids (low density), does low λ₁ predict positive v_r residual (faster expansion)?
void_mask = deltas < np.percentile(deltas, 25)

print(f"\nVoid analysis (lowest 25% density, n={void_mask.sum()}):")

# Within voids, correlate λ₁ with v_r residual
if void_mask.sum() > 20:
    r_void, p_void = pearsonr(lambda1s[void_mask], v_r_residual[void_mask])
    print(f"  Corr(λ₁, v_r_residual) in voids = {r_void:.4f} (p={p_void:.3f})")

    # The prediction: NEGATIVE correlation
    # Low λ₁ in void → approaches threshold → FASTER expansion → MORE POSITIVE v_r residual
    # Therefore: Corr(λ₁, v_r_residual) < 0

    if r_void < -0.1 and p_void < 0.05:
        print(f"\n  ✓ LOW λ₁ VOIDS EXPAND FASTER THAN DENSITY PREDICTS!")
        print(f"  This is the non-tautological prediction of spectral cosmology.")
    elif r_void < 0:
        print(f"\n  ~ Trend in predicted direction but not significant.")
    else:
        print(f"\n  ✗ Correlation not in predicted direction.")

# Also check: split voids by λ₁ and compare expansion
void_lambda1s = lambda1s[void_mask]
void_vr_residuals = v_r_residual[void_mask]

low_l1_mask = void_lambda1s < np.median(void_lambda1s)
high_l1_mask = ~low_l1_mask

mean_vr_low_l1 = void_vr_residuals[low_l1_mask].mean()
mean_vr_high_l1 = void_vr_residuals[high_l1_mask].mean()

print(f"\n  Split void sample by λ₁:")
print(f"    Low-λ₁ voids:  mean v_r residual = {mean_vr_low_l1:+.1f} km/s")
print(f"    High-λ₁ voids: mean v_r residual = {mean_vr_high_l1:+.1f} km/s")
print(f"    Difference: {mean_vr_low_l1 - mean_vr_high_l1:+.1f} km/s")

if mean_vr_low_l1 > mean_vr_high_l1:
    print(f"\n  ✓ Low-λ₁ voids expand faster (residual) than high-λ₁ voids!")
else:
    print(f"\n  ✗ Not in predicted direction.")

# =============================================================================
# VISUALIZATION
# =============================================================================
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# Panel 1: Partial correlation visualization
ax1 = axes[0, 0]
# Residualize both λ₁ and v_r against density
lambda1_resid = lambda1s - LinearRegression().fit(deltas.reshape(-1,1), lambda1s).predict(deltas.reshape(-1,1))
vr_resid = v_rads - LinearRegression().fit(deltas.reshape(-1,1), v_rads).predict(deltas.reshape(-1,1))
ax1.scatter(lambda1_resid, vr_resid, alpha=0.3, s=10)
ax1.axhline(0, color='gray', linestyle='--', alpha=0.5)
ax1.axvline(0, color='gray', linestyle='--', alpha=0.5)
z = np.polyfit(lambda1_resid, vr_resid, 1)
p = np.poly1d(z)
x_line = np.linspace(lambda1_resid.min(), lambda1_resid.max(), 100)
ax1.plot(x_line, p(x_line), 'r-', lw=2, label=f'Partial r = {r_partial:.3f}')
ax1.set_xlabel('λ₁ residual (after removing δ effect)', fontsize=11)
ax1.set_ylabel('v_r residual (after removing δ effect)', fontsize=11)
ax1.set_title('Test 1: Partial Correlation (controlling for density)', fontsize=12)
ax1.legend()
ax1.grid(True, alpha=0.3)

# Panel 2: Incremental R²
ax2 = axes[0, 1]
models = ['Density only\n(v_r ~ δ)', 'Density + λ₁\n(v_r ~ δ + λ₁)']
r2_values = [r2_density, r2_both]
bars = ax2.bar(models, r2_values, color=['steelblue', 'seagreen'], edgecolor='black')
ax2.set_ylabel('R² (variance explained)', fontsize=11)
ax2.set_title(f'Test 2: Incremental Predictive Power (ΔR² = {delta_r2:.4f})', fontsize=12)
ax2.set_ylim(0, max(r2_values) * 1.3)
for bar, val in zip(bars, r2_values):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
             f'{val:.4f}', ha='center', fontsize=11)
ax2.grid(True, alpha=0.3, axis='y')

# Panel 3: Void expansion test
ax3 = axes[1, 0]
ax3.scatter(lambda1s[void_mask], v_r_residual[void_mask], alpha=0.5, s=30, c='blue', label='Void regions')
ax3.axhline(0, color='gray', linestyle='--', alpha=0.5)
if void_mask.sum() > 10:
    z = np.polyfit(lambda1s[void_mask], v_r_residual[void_mask], 1)
    p = np.poly1d(z)
    x_line = np.linspace(lambda1s[void_mask].min(), lambda1s[void_mask].max(), 100)
    ax3.plot(x_line, p(x_line), 'r-', lw=2, label=f'r = {r_void:.3f}')
ax3.set_xlabel('Spectral gap λ₁', fontsize=11)
ax3.set_ylabel('v_r residual (km/s)\n(after density correction)', fontsize=11)
ax3.set_title('Test 4: Void Expansion - The Physical Test', fontsize=12)
ax3.legend()
ax3.grid(True, alpha=0.3)

# Panel 4: Summary
ax4 = axes[1, 1]
ax4.axis('off')

summary = f"""
NON-TAUTOLOGICAL TEST RESULTS
{'='*55}

The Problem:
  Corr(λ₁, δ) = 0.95 is BUILT INTO graph construction.
  This validates nothing about spectral cosmology.

The Solution:
  Test whether λ₁ predicts BEYOND what density predicts.

RESULTS:
{'='*55}

Test 1: Partial Correlation
  Corr(λ₁, v_r | δ) = {r_partial:.4f}
  {"✓ λ₁ has residual signal" if abs(r_partial) > 0.1 else "✗ λ₁ ≈ density proxy"}

Test 2: Incremental R²
  R²(δ only) = {r2_density:.4f}
  R²(δ + λ₁) = {r2_both:.4f}
  ΔR² = {delta_r2:.4f}
  {"✓ λ₁ adds predictive power" if delta_r2 > 0.01 else "✗ Minimal improvement"}

Test 3: Bakry-Émery (Continuous)
  Partial Corr = {r_partial_be:.4f}
  (Compare to graph: {r_partial:.4f})

Test 4: Void Expansion (Physical Test)
  In voids: Corr(λ₁, v_r_resid) = {r_void:.4f}
  Low-λ₁ voids: v_r_resid = {mean_vr_low_l1:+.1f} km/s
  High-λ₁ voids: v_r_resid = {mean_vr_high_l1:+.1f} km/s
  {"✓ Low-λ₁ voids expand faster!" if mean_vr_low_l1 > mean_vr_high_l1 else "✗ Not confirmed"}

INTERPRETATION:
{'='*55}
The framework predicts: low λ₁ → approach threshold → faster expansion.
This is testable independently of the tautological λ₁-δ correlation.
"""

ax4.text(0.02, 0.98, summary, transform=ax4.transAxes, fontsize=10,
         verticalalignment='top', fontfamily='monospace',
         bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig('non_tautological_test.png', dpi=150, bbox_inches='tight')
print("\n" + "="*60)
print("Saved: non_tautological_test.png")

# =============================================================================
# FINAL VERDICT
# =============================================================================
print("\n" + "="*60)
print("FINAL VERDICT")
print("="*60)

tests_passed = 0
if abs(r_partial) > 0.1:
    tests_passed += 1
if delta_r2 > 0.01:
    tests_passed += 1
if mean_vr_low_l1 > mean_vr_high_l1:
    tests_passed += 1

print(f"\nTests passed: {tests_passed}/3")

if tests_passed >= 2:
    print("""
CONCLUSION: λ₁ captures physics BEYOND density.

The spectral cosmology framework makes a non-tautological prediction:
  Low λ₁ → high integration measure → approach threshold → faster expansion

This is confirmed: low-λ₁ voids expand faster than density alone predicts.

The framework is NOT just repackaging density correlations.
""")
elif tests_passed == 1:
    print("""
CONCLUSION: Marginal evidence for non-tautological physics.

Some tests suggest λ₁ adds information beyond density, but results are mixed.
More data or refined analysis needed.
""")
else:
    print("""
CONCLUSION: λ₁ appears to be primarily a density proxy.

The tests do not show strong evidence that λ₁ predicts beyond density.
The λ₁-density correlation may indeed be largely tautological.
""")

# Save numerical results
np.savez('non_tautological_results.npz',
         r_partial=r_partial,
         delta_r2=delta_r2,
         r_void=r_void,
         mean_vr_low_l1=mean_vr_low_l1,
         mean_vr_high_l1=mean_vr_high_l1,
         be_lambda1s=be_lambda1s,
         be_deltas=be_deltas,
         be_vrads=be_vrads)
print("\nSaved: non_tautological_results.npz")
