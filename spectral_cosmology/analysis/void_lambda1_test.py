#!/usr/bin/env python3
"""
ALTERNATIVE TEST: λ₁ from Void Structure vs Predicted H

Uses VAST VoidFinder catalog to:
1. Compute local λ₁ from void + galaxy distribution
2. Compare void properties with predicted expansion rates

This test uses real void positions/sizes from SDSS DR7 data.

Author: Aaron Ben-Shalom & Claude
Date: January 2026
"""

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
from scipy.stats import pearsonr, spearmanr
import matplotlib.pyplot as plt

print("=" * 70)
print("ALTERNATIVE TEST: λ₁ FROM VOID STRUCTURE")
print("Using VAST VoidFinder Catalog")
print("=" * 70)

# =============================================================================
# LOAD VOID CATALOG
# =============================================================================

print("\n1. Loading void catalog...")

# Load void holes (spheres that make up voids)
holes = np.loadtxt('VoidFinder_holes.txt', skiprows=1)
print(f"Loaded {len(holes)} void sphere components")
print(f"Columns: x, y, z, radius, void_id")

# Load maximal spheres (largest sphere in each void)
maximal = np.loadtxt('VoidFinder_maximal.txt', skiprows=1)
print(f"Loaded {len(maximal)} maximal void spheres")

# Load galaxy-void membership
galzones = np.loadtxt('V2_galzones.dat', skiprows=1)
print(f"Loaded {len(galzones)} galaxy-zone assignments")

# Count unique voids
void_ids = np.unique(holes[:, 4])
n_voids = len(void_ids)
print(f"Number of unique voids: {n_voids}")

# =============================================================================
# COMPUTE PROPERTIES FOR EACH VOID
# =============================================================================

print("\n2. Computing void properties...")

# For each void, compute:
# - Effective radius (from maximal sphere or weighted average)
# - Volume
# - Number of component spheres
# - Position (center of mass)

void_props = {}

for vid in void_ids:
    mask = holes[:, 4] == vid
    void_holes = holes[mask]

    # Center of mass
    x_cm = np.mean(void_holes[:, 0])
    y_cm = np.mean(void_holes[:, 1])
    z_cm = np.mean(void_holes[:, 2])

    # Effective radius (largest sphere radius)
    r_max = np.max(void_holes[:, 3])

    # Mean radius
    r_mean = np.mean(void_holes[:, 3])

    # Number of components
    n_components = len(void_holes)

    # Distance from origin (observer)
    dist = np.sqrt(x_cm**2 + y_cm**2 + z_cm**2)

    void_props[vid] = {
        'center': (x_cm, y_cm, z_cm),
        'r_max': r_max,
        'r_mean': r_mean,
        'n_components': n_components,
        'distance': dist,
        'holes': void_holes
    }

# Filter to voids with reasonable distance (50-400 Mpc/h)
valid_voids = {k: v for k, v in void_props.items()
               if 50 < v['distance'] < 400 and v['n_components'] >= 3}

print(f"Voids in distance range 50-400 Mpc/h with >= 3 components: {len(valid_voids)}")

# =============================================================================
# COMPUTE λ₁ FOR EACH VOID'S LOCAL STRUCTURE
# =============================================================================

print("\n3. Computing spectral gap λ₁ for each void...")

def compute_void_lambda1(void_holes, sigma=10.0):
    """
    Compute λ₁ from the void's internal structure (sphere connectivity graph).

    Lower λ₁ = more fragmented structure = less connected = void-like
    Higher λ₁ = more connected structure = more filled = cluster-like
    """
    n = len(void_holes)
    if n < 3:
        return np.nan

    # Build adjacency matrix: connect overlapping or nearby spheres
    rows, cols, weights = [], [], []

    for i in range(n):
        xi, yi, zi, ri = void_holes[i, :4]
        for j in range(i + 1, n):
            xj, yj, zj, rj = void_holes[j, :4]

            # Distance between sphere centers
            d = np.sqrt((xi - xj)**2 + (yi - yj)**2 + (zi - zj)**2)

            # Connection strength: higher if spheres overlap or are close
            # Spheres overlap if d < ri + rj
            overlap = (ri + rj) - d

            if overlap > -sigma:  # Connect if overlapping or within sigma
                # Weight by overlap amount
                w = np.exp(overlap / sigma)
                rows.extend([i, j])
                cols.extend([j, i])
                weights.extend([w, w])

    if len(rows) == 0:
        return np.nan

    W = csr_matrix((weights, (rows, cols)), shape=(n, n))
    D = np.array(W.sum(axis=1)).flatten()
    D_sparse = csr_matrix((D, (range(n), range(n))), shape=(n, n))
    L = D_sparse - W

    try:
        k = min(3, n - 1)
        eigenvalues, _ = eigsh(L, k=k, which='SM', maxiter=1000)
        eigenvalues = np.sort(np.abs(eigenvalues))
        for ev in eigenvalues[1:]:
            if ev > 1e-10:
                return ev
        return eigenvalues[1] if len(eigenvalues) > 1 else np.nan
    except:
        return np.nan

results = []

for vid, props in valid_voids.items():
    lambda1 = compute_void_lambda1(props['holes'])

    if np.isnan(lambda1) or lambda1 < 1e-10:
        continue

    # Expected H for this void based on size (larger voids → higher H in our framework)
    # H_void = H0 * (1 + alpha/r^2) approximately
    # For now, use r_max as proxy for void emptiness

    results.append({
        'void_id': vid,
        'lambda1': lambda1,
        'r_max': props['r_max'],
        'r_mean': props['r_mean'],
        'n_components': props['n_components'],
        'distance': props['distance'],
        'center': props['center']
    })

print(f"Computed λ₁ for {len(results)} voids")

# =============================================================================
# ANALYSIS
# =============================================================================

print("\n4. Analyzing correlations...")

if len(results) < 10:
    print("ERROR: Insufficient valid voids for analysis")
else:
    lambda1_arr = np.array([r['lambda1'] for r in results])
    r_max_arr = np.array([r['r_max'] for r in results])
    r_mean_arr = np.array([r['r_mean'] for r in results])
    n_comp_arr = np.array([r['n_components'] for r in results])
    dist_arr = np.array([r['distance'] for r in results])

    # Key correlations
    r_size, p_size = pearsonr(lambda1_arr, r_max_arr)
    r_ncomp, p_ncomp = pearsonr(lambda1_arr, n_comp_arr)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print(f"\nSample size: {len(results)} voids")

    print(f"\nλ₁ statistics:")
    print(f"  Mean: {np.mean(lambda1_arr):.4f}")
    print(f"  Std:  {np.std(lambda1_arr):.4f}")
    print(f"  Range: {np.min(lambda1_arr):.4f} to {np.max(lambda1_arr):.4f}")

    print(f"\nVoid size statistics (r_max in Mpc/h):")
    print(f"  Mean: {np.mean(r_max_arr):.1f}")
    print(f"  Range: {np.min(r_max_arr):.1f} to {np.max(r_max_arr):.1f}")

    print(f"\n*** KEY CORRELATIONS ***")
    print(f"  λ₁ vs r_max (void size):      r = {r_size:.3f} (p = {p_size:.2e})")
    print(f"  λ₁ vs n_components:           r = {r_ncomp:.3f} (p = {p_ncomp:.2e})")

    # PREDICTION: Larger voids should have LOWER λ₁ (more fragmented)
    # This gives them higher I_e, closer to threshold, hence faster expansion

    print("\n" + "-" * 70)
    if r_size < -0.2 and p_size < 0.05:
        print("✓ PREDICTION SUPPORTED: Larger voids have LOWER λ₁")
        print("  This means larger voids are more fragmented (spectrally)")
        print("  → Higher integration I_e → Closer to threshold → Faster expansion")
    elif r_size > 0.2 and p_size < 0.05:
        print("? UNEXPECTED: Larger voids have HIGHER λ₁")
        print("  This contradicts the simple fragmentation expectation")
    else:
        print(f"? INCONCLUSIVE: No significant correlation (r = {r_size:.3f})")
    print("-" * 70)

    # Split by void size
    large_mask = r_max_arr > np.median(r_max_arr)
    small_mask = ~large_mask

    print(f"\nLarge voids (r > {np.median(r_max_arr):.1f} Mpc/h): n = {np.sum(large_mask)}")
    print(f"  Mean λ₁: {np.mean(lambda1_arr[large_mask]):.4f}")

    print(f"\nSmall voids (r <= {np.median(r_max_arr):.1f} Mpc/h): n = {np.sum(small_mask)}")
    print(f"  Mean λ₁: {np.mean(lambda1_arr[small_mask]):.4f}")

    ratio = np.mean(lambda1_arr[small_mask]) / np.mean(lambda1_arr[large_mask])
    print(f"\nRatio λ₁(small)/λ₁(large) = {ratio:.2f}")

    # =============================================================================
    # VISUALIZATION
    # =============================================================================

    print("\n5. Creating visualizations...")

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Panel 1: λ₁ vs void size
    ax1 = axes[0, 0]
    scatter = ax1.scatter(r_max_arr, lambda1_arr, c=n_comp_arr, cmap='viridis',
                         s=50, alpha=0.7, edgecolors='k', linewidth=0.5)

    z = np.polyfit(r_max_arr, lambda1_arr, 1)
    p = np.poly1d(z)
    x_fit = np.linspace(r_max_arr.min(), r_max_arr.max(), 100)
    ax1.plot(x_fit, p(x_fit), 'r-', linewidth=2, label=f'Linear fit (r={r_size:.2f})')

    ax1.set_xlabel('Void Radius r_max [Mpc/h]', fontsize=12)
    ax1.set_ylabel('Spectral Gap λ₁', fontsize=12)
    ax1.set_title('λ₁ vs Void Size\n(VAST VoidFinder Catalog)', fontsize=14)
    ax1.legend()
    plt.colorbar(scatter, ax=ax1, label='# Components')
    ax1.grid(True, alpha=0.3)

    # Panel 2: λ₁ histogram by void size
    ax2 = axes[0, 1]
    ax2.hist(lambda1_arr[large_mask], bins=20, alpha=0.6, label='Large voids', color='blue')
    ax2.hist(lambda1_arr[small_mask], bins=20, alpha=0.6, label='Small voids', color='red')
    ax2.set_xlabel('Spectral Gap λ₁', fontsize=12)
    ax2.set_ylabel('Count', fontsize=12)
    ax2.set_title('λ₁ Distribution by Void Size', fontsize=14)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Panel 3: Void positions
    ax3 = axes[1, 0]
    centers = np.array([r['center'] for r in results])
    scatter = ax3.scatter(centers[:, 0], centers[:, 1], c=lambda1_arr, cmap='coolwarm',
                         s=r_max_arr * 2, alpha=0.6, edgecolors='k', linewidth=0.3)
    ax3.set_xlabel('X [Mpc/h]', fontsize=12)
    ax3.set_ylabel('Y [Mpc/h]', fontsize=12)
    ax3.set_title('Void Positions (color = λ₁, size = r_max)', fontsize=14)
    plt.colorbar(scatter, ax=ax3, label='λ₁')
    ax3.set_aspect('equal')
    ax3.grid(True, alpha=0.3)

    # Panel 4: Summary
    ax4 = axes[1, 1]
    ax4.axis('off')

    summary = f"""
    VOID STRUCTURE SPECTRAL ANALYSIS
    ══════════════════════════════════════════

    DATA: VAST VoidFinder Catalog (SDSS DR7)
      Voids analyzed: {len(results)}
      Distance range: 50-400 Mpc/h

    PREDICTION (Spectral Cosmology):
      Larger voids → more fragmented → lower λ₁
      Lower λ₁ → higher I_e → faster expansion

    RESULT:
      Corr(λ₁, r_max) = {r_size:+.3f} (p = {p_size:.2e})

      Large voids: λ₁ = {np.mean(lambda1_arr[large_mask]):.4f}
      Small voids: λ₁ = {np.mean(lambda1_arr[small_mask]):.4f}
      Ratio: {ratio:.2f}

    INTERPRETATION:
    """

    if r_size < -0.2 and p_size < 0.05:
        summary += "  ✓ Large voids have lower λ₁ as predicted\n"
        summary += "  Supports spectral cosmology framework"
    else:
        summary += f"  Correlation: {r_size:+.3f}\n"
        summary += "  Further analysis needed"

    ax4.text(0.05, 0.95, summary, transform=ax4.transAxes, fontsize=11,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

    plt.tight_layout()
    plt.savefig('void_lambda1_analysis.png', dpi=150, bbox_inches='tight')
    print("Saved: void_lambda1_analysis.png")

print("\n" + "=" * 70)
print("VOID STRUCTURE ANALYSIS COMPLETE")
print("=" * 70)
