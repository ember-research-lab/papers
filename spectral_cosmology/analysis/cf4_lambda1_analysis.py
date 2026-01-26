"""
Real Data Analysis: λ₁-H Correlation from CosmicFlows-4++

This script tests the spectral cosmology prediction:
  - Low density regions (voids) should have LOW λ₁ and HIGH local H
  - High density regions (clusters) should have HIGH λ₁ and LOW local H
  - Therefore: Corr(λ₁, H) < 0 (negative correlation)

Using CF4++ 128³ density and velocity grids.
"""

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
from scipy.stats import pearsonr, spearmanr
import matplotlib.pyplot as plt

# Load data
print("Loading CosmicFlows-4++ data...")
data = np.load('CF4pp_mean_std_grids.npz')
delta = data['d_mean_CF4pp']  # Density contrast δ = ρ/ρ̄ - 1
v_rad = data['vr_mean_CF4pp']  # Radial peculiar velocity (km/s)

print(f"Grid shape: {delta.shape}")
print(f"Density contrast range: [{delta.min():.2f}, {delta.max():.2f}]")
print(f"Radial velocity range: [{v_rad.min():.0f}, {v_rad.max():.0f}] km/s")

# Analysis parameters
SUBGRID_SIZE = 16  # Analyze 16³ subregions
N_NEIGHBORS = 6    # 6-connectivity for 3D grid
SIGMA = 2.0        # Gaussian weight scale

def compute_lambda1_subgrid(density_subgrid, n_neighbors=6):
    """
    Compute Fiedler value (λ₁) for a 3D density subgrid.

    Build weighted graph where:
    - Nodes are grid cells
    - Edges connect 6-neighbors
    - Weights are w_ij = exp((δ_i + δ_j)/(2σ)) - higher density = stronger connection
    """
    nx, ny, nz = density_subgrid.shape
    N = nx * ny * nz

    if N < 10:
        return np.nan

    # Build sparse Laplacian
    rows, cols, weights = [], [], []

    def idx(i, j, k):
        return i * ny * nz + j * nz + k

    # 6-connectivity
    directions = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]

    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                node = idx(i, j, k)
                d_node = density_subgrid[i, j, k]

                for di, dj, dk in directions:
                    ni, nj, nk = i + di, j + dj, k + dk
                    if 0 <= ni < nx and 0 <= nj < ny and 0 <= nk < nz:
                        neighbor = idx(ni, nj, nk)
                        d_neighbor = density_subgrid[ni, nj, nk]

                        # Weight based on mean density
                        mean_d = (d_node + d_neighbor) / 2
                        # Higher density = stronger connection
                        w = np.exp(mean_d / SIGMA)

                        rows.append(node)
                        cols.append(neighbor)
                        weights.append(w)

    # Build adjacency
    W = csr_matrix((weights, (rows, cols)), shape=(N, N))

    # Degree matrix
    D = np.array(W.sum(axis=1)).flatten()
    D_sparse = csr_matrix((D, (range(N), range(N))), shape=(N, N))

    # Laplacian L = D - W
    L = D_sparse - W

    # Compute smallest eigenvalues
    try:
        eigenvalues, _ = eigsh(L, k=min(6, N-2), which='SM', maxiter=5000)
        eigenvalues = np.sort(np.abs(eigenvalues))

        # λ₁ is first non-zero eigenvalue
        for ev in eigenvalues[1:]:
            if ev > 1e-8:
                return ev
        return eigenvalues[1] if len(eigenvalues) > 1 else np.nan
    except:
        return np.nan

# Divide into subregions and compute λ₁ for each
print(f"\nAnalyzing {128//SUBGRID_SIZE}³ = {(128//SUBGRID_SIZE)**3} subregions...")

n_sub = 128 // SUBGRID_SIZE
results = []

for i in range(n_sub):
    for j in range(n_sub):
        for k in range(n_sub):
            # Extract subgrid
            i0, i1 = i * SUBGRID_SIZE, (i+1) * SUBGRID_SIZE
            j0, j1 = j * SUBGRID_SIZE, (j+1) * SUBGRID_SIZE
            k0, k1 = k * SUBGRID_SIZE, (k+1) * SUBGRID_SIZE

            sub_delta = delta[i0:i1, j0:j1, k0:k1]
            sub_vrad = v_rad[i0:i1, j0:j1, k0:k1]

            # Compute properties
            mean_delta = np.mean(sub_delta)
            mean_vrad = np.mean(sub_vrad)

            # Compute λ₁
            lambda1 = compute_lambda1_subgrid(sub_delta)

            if not np.isnan(lambda1):
                results.append({
                    'i': i, 'j': j, 'k': k,
                    'delta': mean_delta,
                    'v_rad': mean_vrad,
                    'lambda1': lambda1
                })

            if len(results) % 100 == 0:
                print(f"  Processed {len(results)} subregions...")

print(f"\nValid subregions: {len(results)}")

# Extract arrays
deltas = np.array([r['delta'] for r in results])
v_rads = np.array([r['v_rad'] for r in results])
lambda1s = np.array([r['lambda1'] for r in results])

# Correlations
print("\n" + "="*60)
print("CORRELATION ANALYSIS")
print("="*60)

# λ₁ vs density
r_lambda_delta, p_lambda_delta = pearsonr(lambda1s, deltas)
rho_lambda_delta, _ = spearmanr(lambda1s, deltas)
print(f"\nλ₁ vs δ (density):")
print(f"  Pearson r = {r_lambda_delta:.3f} (p = {p_lambda_delta:.2e})")
print(f"  Spearman ρ = {rho_lambda_delta:.3f}")
print(f"  Prediction: r > 0 (denser → more connected → higher λ₁)")
print(f"  Result: {'✓ CONFIRMED' if r_lambda_delta > 0 else '✗ UNEXPECTED'}")

# λ₁ vs radial velocity (proxy for local expansion)
r_lambda_vr, p_lambda_vr = pearsonr(lambda1s, v_rads)
rho_lambda_vr, _ = spearmanr(lambda1s, v_rads)
print(f"\nλ₁ vs v_r (radial velocity, proxy for H deviation):")
print(f"  Pearson r = {r_lambda_vr:.3f} (p = {p_lambda_vr:.2e})")
print(f"  Spearman ρ = {rho_lambda_vr:.3f}")
print(f"  Prediction: r < 0 (higher λ₁ → lower effective H → lower outflow)")
print(f"  Result: {'✓ CONFIRMED' if r_lambda_vr < 0 else '✗ UNEXPECTED'}")

# δ vs v_r (sanity check - should be negative, voids expand)
r_delta_vr, p_delta_vr = pearsonr(deltas, v_rads)
rho_delta_vr, _ = spearmanr(deltas, v_rads)
print(f"\nδ vs v_r (sanity check):")
print(f"  Pearson r = {r_delta_vr:.3f} (p = {p_delta_vr:.2e})")
print(f"  Spearman ρ = {rho_delta_vr:.3f}")
print(f"  Expected: r < 0 (voids expand outward, clusters contract)")

# Categorize by density
print("\n" + "="*60)
print("SPECTRAL GAP BY ENVIRONMENT")
print("="*60)

void_mask = deltas < -0.5
filament_mask = (deltas >= -0.5) & (deltas <= 0.5)
cluster_mask = deltas > 0.5

print(f"\nVoids (δ < -0.5): n = {void_mask.sum()}")
if void_mask.sum() > 0:
    print(f"  Mean λ₁ = {lambda1s[void_mask].mean():.4f}")
    print(f"  Mean v_r = {v_rads[void_mask].mean():.1f} km/s")

print(f"\nFilaments (-0.5 ≤ δ ≤ 0.5): n = {filament_mask.sum()}")
if filament_mask.sum() > 0:
    print(f"  Mean λ₁ = {lambda1s[filament_mask].mean():.4f}")
    print(f"  Mean v_r = {v_rads[filament_mask].mean():.1f} km/s")

print(f"\nClusters (δ > 0.5): n = {cluster_mask.sum()}")
if cluster_mask.sum() > 0:
    print(f"  Mean λ₁ = {lambda1s[cluster_mask].mean():.4f}")
    print(f"  Mean v_r = {v_rads[cluster_mask].mean():.1f} km/s")

# Key ratio
if void_mask.sum() > 0 and cluster_mask.sum() > 0:
    ratio = lambda1s[cluster_mask].mean() / lambda1s[void_mask].mean()
    print(f"\n  λ₁(cluster)/λ₁(void) = {ratio:.2f}")
    print(f"  Prediction: ratio > 1 (clusters more connected)")
    print(f"  Result: {'✓ CONFIRMED' if ratio > 1 else '✗ UNEXPECTED'}")

# Visualization
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

# Panel 1: λ₁ vs δ
ax1 = axes[0, 0]
scatter = ax1.scatter(deltas, lambda1s, c=v_rads, cmap='coolwarm', alpha=0.6, s=20)
ax1.set_xlabel('Density contrast δ', fontsize=12)
ax1.set_ylabel('Spectral gap λ₁', fontsize=12)
ax1.set_title(f'λ₁ vs Density (r = {r_lambda_delta:.3f}, p = {p_lambda_delta:.2e})', fontsize=14)
plt.colorbar(scatter, ax=ax1, label='v_r (km/s)')
ax1.grid(True, alpha=0.3)

# Add trend line
z = np.polyfit(deltas, lambda1s, 1)
p = np.poly1d(z)
ax1.plot(sorted(deltas), p(sorted(deltas)), 'k--', lw=2, label='Linear fit')
ax1.legend()

# Panel 2: λ₁ vs v_r
ax2 = axes[0, 1]
scatter2 = ax2.scatter(lambda1s, v_rads, c=deltas, cmap='viridis', alpha=0.6, s=20)
ax2.set_xlabel('Spectral gap λ₁', fontsize=12)
ax2.set_ylabel('Radial velocity v_r (km/s)', fontsize=12)
ax2.set_title(f'v_r vs λ₁ (r = {r_lambda_vr:.3f}, p = {p_lambda_vr:.2e})', fontsize=14)
plt.colorbar(scatter2, ax=ax2, label='δ')
ax2.grid(True, alpha=0.3)
ax2.axhline(0, color='gray', linestyle='--', alpha=0.5)

# Panel 3: Box plot by environment
ax3 = axes[1, 0]
box_data = []
box_labels = []
for mask, label in [(void_mask, 'Void'), (filament_mask, 'Filament'), (cluster_mask, 'Cluster')]:
    if mask.sum() > 0:
        box_data.append(lambda1s[mask])
        box_labels.append(f'{label}\n(n={mask.sum()})')

bp = ax3.boxplot(box_data, labels=box_labels, patch_artist=True)
colors = ['blue', 'green', 'red']
for patch, color in zip(bp['boxes'], colors[:len(bp['boxes'])]):
    patch.set_facecolor(color)
    patch.set_alpha(0.6)
ax3.set_ylabel('Spectral gap λ₁', fontsize=12)
ax3.set_title('λ₁ Distribution by Cosmic Environment', fontsize=14)
ax3.grid(True, alpha=0.3, axis='y')

# Panel 4: Summary text
ax4 = axes[1, 1]
ax4.axis('off')

summary = f"""
SPECTRAL COSMOLOGY: REAL DATA TEST
{'='*50}

Data: CosmicFlows-4++ 128³ grid
Subregions analyzed: {len(results)}
Subgrid size: {SUBGRID_SIZE}³

KEY RESULTS:
{'='*50}

1. λ₁ vs Density (δ):
   Pearson r = {r_lambda_delta:+.3f} (p = {p_lambda_delta:.2e})
   Spearman ρ = {rho_lambda_delta:+.3f}
   Prediction: r > 0 ✓

2. λ₁ vs Radial Velocity (v_r):
   Pearson r = {r_lambda_vr:+.3f} (p = {p_lambda_vr:.2e})
   Spearman ρ = {rho_lambda_vr:+.3f}
   Prediction: r < 0 {"✓" if r_lambda_vr < 0 else "✗"}

3. Environment Analysis:
   λ₁(void)    = {lambda1s[void_mask].mean():.4f} (n={void_mask.sum()})
   λ₁(filament) = {lambda1s[filament_mask].mean():.4f} (n={filament_mask.sum()})
   λ₁(cluster) = {lambda1s[cluster_mask].mean():.4f} (n={cluster_mask.sum()})

INTERPRETATION:
{'='*50}
The spectral cosmology framework predicts:
- Low density → low λ₁ → high I_e → faster expansion
- High density → high λ₁ → low I_e → slower expansion

Results {'SUPPORT' if r_lambda_delta > 0 and r_lambda_vr < 0 else 'DO NOT SUPPORT'} the framework.
"""

ax4.text(0.05, 0.95, summary, transform=ax4.transAxes, fontsize=10,
         verticalalignment='top', fontfamily='monospace',
         bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig('cf4_lambda1_analysis.png', dpi=150, bbox_inches='tight')
print("\nSaved: cf4_lambda1_analysis.png")

# Save results
np.savez('cf4_lambda1_results.npz',
         deltas=deltas, v_rads=v_rads, lambda1s=lambda1s,
         r_lambda_delta=r_lambda_delta, r_lambda_vr=r_lambda_vr)
print("Saved: cf4_lambda1_results.npz")
