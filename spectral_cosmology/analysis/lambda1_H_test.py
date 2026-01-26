#!/usr/bin/env python3
"""
NOVEL TEST: λ₁-H Correlation from Real CosmicFlows-4 Data

This script performs the critical falsification test for spectral cosmology:
- Compute spectral gap λ₁ from local density structure
- Get local Hubble parameter from peculiar velocities
- Test for anti-correlation between λ₁ and H

Using real CosmicFlows-4++ data (Courtois et al. 2025)

Author: Aaron Ben-Shalom & Claude
Date: January 2026
"""

import numpy as np
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import eigsh
from scipy.ndimage import gaussian_filter
from scipy.stats import pearsonr, spearmanr
import matplotlib.pyplot as plt

print("=" * 70)
print("NOVEL TEST: λ₁-H CORRELATION FROM REAL COSMICFLOWS-4 DATA")
print("=" * 70)

# =============================================================================
# LOAD COSMICFLOWS-4++ DATA
# =============================================================================

print("\n1. Loading CosmicFlows-4++ data...")
data = np.load('CF4pp_mean_std_grids.npz')

print("Available fields:", list(data.keys()))

# Extract the grids
delta_mean = data['d_mean_CF4pp']     # Density contrast δ = (ρ - ρ̄)/ρ̄
delta_std = data['d_std_CF4pp']       # Uncertainty in δ
v_mean = data['v_mean_CF4pp']         # Cartesian velocities (3, 128, 128, 128)
v_std = data['v_std_CF4pp']           # Velocity uncertainties
vr_mean = data['vr_mean_CF4pp']       # Radial velocities
vr_std = data['vr_std_CF4pp']         # Radial velocity uncertainties

print(f"Density grid shape: {delta_mean.shape}")
print(f"Velocity grid shape: {v_mean.shape}")

# Grid parameters
N = 128
L = 1000  # Mpc/h total box size
cell_size = L / N  # ~7.8 Mpc/h per cell

print(f"Grid: {N}³ cells, {L} Mpc/h box, {cell_size:.1f} Mpc/h resolution")

# =============================================================================
# COSMOLOGY CONSTANTS
# =============================================================================

H0_planck = 67.4  # km/s/Mpc (Planck 2018)
c = 299792.458    # km/s

# =============================================================================
# COMPUTE LOCAL λ₁ FROM DENSITY STRUCTURE
# =============================================================================

def compute_local_lambda1(delta_patch, sigma=1.0):
    """
    Compute spectral gap λ₁ from a local density patch using graph Laplacian.

    The density field defines edge weights: higher density contrast → stronger connections.
    """
    n = delta_patch.shape[0]
    if n < 4:
        return np.nan

    # Flatten to 1D for graph construction
    flat = delta_patch.flatten()
    n_nodes = len(flat)

    if n_nodes < 10:
        return np.nan

    # Build adjacency matrix: connect neighboring cells
    # Weight by density: w_ij = exp(-(|δ_i - δ_j|²) / (2σ²)) * connectivity_factor
    rows, cols, weights = [], [], []

    # 3D grid neighbors (6-connectivity)
    for i in range(n):
        for j in range(n):
            for k in range(n):
                idx = i * n * n + j * n + k

                # Connect to neighbors
                for di, dj, dk in [(1,0,0), (0,1,0), (0,0,1)]:
                    ni, nj, nk = i + di, j + dj, k + dk
                    if 0 <= ni < n and 0 <= nj < n and 0 <= nk < n:
                        neighbor_idx = ni * n * n + nj * n + nk

                        # Weight based on density: denser → stronger connection
                        # Use mean density between cells as connection strength
                        mean_delta = (delta_patch[i,j,k] + delta_patch[ni,nj,nk]) / 2
                        # Transform δ ∈ (-1, ∞) to positive weight
                        # Higher δ → higher density → higher connectivity
                        w = np.exp(mean_delta / sigma)

                        rows.extend([idx, neighbor_idx])
                        cols.extend([neighbor_idx, idx])
                        weights.extend([w, w])

    if len(rows) == 0:
        return np.nan

    W = csr_matrix((weights, (rows, cols)), shape=(n_nodes, n_nodes))
    D = np.array(W.sum(axis=1)).flatten()
    D_sparse = csr_matrix((D, (range(n_nodes), range(n_nodes))), shape=(n_nodes, n_nodes))
    L = D_sparse - W

    try:
        eigenvalues, _ = eigsh(L, k=min(6, n_nodes-1), which='SM', maxiter=3000)
        eigenvalues = np.sort(np.abs(eigenvalues))
        # Return first non-zero eigenvalue
        for ev in eigenvalues[1:]:
            if ev > 1e-10:
                return ev
        return eigenvalues[1] if len(eigenvalues) > 1 else np.nan
    except Exception:
        return np.nan

# =============================================================================
# COMPUTE LOCAL HUBBLE PARAMETER FROM VELOCITIES
# =============================================================================

def compute_local_H(vr, d, H0=H0_planck):
    """
    Compute local Hubble parameter from radial peculiar velocity and distance.

    H_local = (c*z) / d = (H0*d + v_pec) / d = H0 + v_pec/d

    Parameters:
    - vr: radial peculiar velocity (km/s)
    - d: comoving distance (Mpc)
    - H0: background Hubble constant

    Returns: H_local (km/s/Mpc)
    """
    if d < 1:  # Avoid division by very small numbers
        return np.nan
    return H0 + vr / d

# =============================================================================
# SAMPLE REGIONS AND COMPUTE λ₁ vs H
# =============================================================================

print("\n2. Sampling regions and computing λ₁ vs H...")

# Sample patches of different sizes
patch_size = 10  # cells (10 × 7.8 = 78 Mpc/h)
n_samples = 200

# Exclude edge regions and center (where CF4 has best data: 100-400 Mpc)
margin = 20  # cells from edge
center = N // 2

results = []

np.random.seed(42)

for i in range(n_samples * 3):  # Oversample, filter later
    # Random position (avoiding edges)
    cx = np.random.randint(margin, N - margin - patch_size)
    cy = np.random.randint(margin, N - margin - patch_size)
    cz = np.random.randint(margin, N - margin - patch_size)

    # Extract patch
    delta_patch = delta_mean[cx:cx+patch_size, cy:cy+patch_size, cz:cz+patch_size]

    # Skip if too much missing data or extreme values
    if np.any(np.isnan(delta_patch)) or np.any(np.abs(delta_patch) > 10):
        continue

    # Compute λ₁
    lambda1 = compute_local_lambda1(delta_patch)
    if np.isnan(lambda1) or lambda1 < 1e-10:
        continue

    # Get center position in supergalactic coords
    sgx = (cx + patch_size/2 - center) * cell_size
    sgy = (cy + patch_size/2 - center) * cell_size
    sgz = (cz + patch_size/2 - center) * cell_size

    # Distance from origin (us)
    d = np.sqrt(sgx**2 + sgy**2 + sgz**2)

    # Skip very nearby (d < 20 Mpc) or far (d > 400 Mpc)
    if d < 20 or d > 400:
        continue

    # Get radial velocity at center
    cx_c, cy_c, cz_c = cx + patch_size//2, cy + patch_size//2, cz + patch_size//2
    vr = vr_mean[cx_c, cy_c, cz_c]
    vr_err = vr_std[cx_c, cy_c, cz_c]

    # Skip if velocity error is too large
    if np.isnan(vr) or np.isnan(vr_err) or vr_err > 500:
        continue

    # Compute local H
    H_local = compute_local_H(vr, d)
    if np.isnan(H_local) or H_local < 30 or H_local > 150:
        continue

    # Mean density in patch
    mean_delta = np.mean(delta_patch)

    results.append({
        'lambda1': lambda1,
        'H_local': H_local,
        'vr': vr,
        'distance': d,
        'mean_delta': mean_delta,
        'position': (sgx, sgy, sgz)
    })

    if len(results) >= n_samples:
        break

print(f"Collected {len(results)} valid samples")

if len(results) < 30:
    print("WARNING: Too few samples. Trying with smaller patches...")
    patch_size = 6
    for i in range(n_samples * 5):
        cx = np.random.randint(margin, N - margin - patch_size)
        cy = np.random.randint(margin, N - margin - patch_size)
        cz = np.random.randint(margin, N - margin - patch_size)

        delta_patch = delta_mean[cx:cx+patch_size, cy:cy+patch_size, cz:cz+patch_size]

        if np.any(np.isnan(delta_patch)) or np.any(np.abs(delta_patch) > 10):
            continue

        lambda1 = compute_local_lambda1(delta_patch)
        if np.isnan(lambda1) or lambda1 < 1e-10:
            continue

        sgx = (cx + patch_size/2 - center) * cell_size
        sgy = (cy + patch_size/2 - center) * cell_size
        sgz = (cz + patch_size/2 - center) * cell_size
        d = np.sqrt(sgx**2 + sgy**2 + sgz**2)

        if d < 20 or d > 400:
            continue

        cx_c, cy_c, cz_c = cx + patch_size//2, cy + patch_size//2, cz + patch_size//2
        vr = vr_mean[cx_c, cy_c, cz_c]
        vr_err = vr_std[cx_c, cy_c, cz_c]

        if np.isnan(vr) or np.isnan(vr_err) or vr_err > 500:
            continue

        H_local = compute_local_H(vr, d)
        if np.isnan(H_local) or H_local < 30 or H_local > 150:
            continue

        mean_delta = np.mean(delta_patch)

        results.append({
            'lambda1': lambda1,
            'H_local': H_local,
            'vr': vr,
            'distance': d,
            'mean_delta': mean_delta,
            'position': (sgx, sgy, sgz)
        })

        if len(results) >= n_samples:
            break

    print(f"After smaller patches: {len(results)} valid samples")

# =============================================================================
# ANALYSIS
# =============================================================================

print("\n3. Analyzing λ₁-H correlation...")

if len(results) < 10:
    print("ERROR: Insufficient data for analysis")
else:
    lambda1_arr = np.array([r['lambda1'] for r in results])
    H_arr = np.array([r['H_local'] for r in results])
    delta_arr = np.array([r['mean_delta'] for r in results])
    d_arr = np.array([r['distance'] for r in results])

    # Compute correlations
    r_pearson, p_pearson = pearsonr(lambda1_arr, H_arr)
    r_spearman, p_spearman = spearmanr(lambda1_arr, H_arr)

    # Also check λ₁ vs density (should be positive)
    r_delta, p_delta = pearsonr(lambda1_arr, delta_arr)

    print("\n" + "=" * 70)
    print("RESULTS: THE CRITICAL TEST")
    print("=" * 70)

    print(f"\nSample size: {len(results)}")
    print(f"\nλ₁ statistics:")
    print(f"  Mean: {np.mean(lambda1_arr):.4f}")
    print(f"  Std:  {np.std(lambda1_arr):.4f}")
    print(f"  Range: {np.min(lambda1_arr):.4f} to {np.max(lambda1_arr):.4f}")

    print(f"\nH_local statistics:")
    print(f"  Mean: {np.mean(H_arr):.1f} km/s/Mpc")
    print(f"  Std:  {np.std(H_arr):.1f} km/s/Mpc")
    print(f"  Range: {np.min(H_arr):.1f} to {np.max(H_arr):.1f} km/s/Mpc")

    print(f"\n*** CRITICAL CORRELATION: λ₁ vs H ***")
    print(f"  Pearson r  = {r_pearson:.3f} (p = {p_pearson:.2e})")
    print(f"  Spearman ρ = {r_spearman:.3f} (p = {p_spearman:.2e})")

    print(f"\nControl: λ₁ vs δ (should be positive):")
    print(f"  Pearson r = {r_delta:.3f} (p = {p_delta:.2e})")

    print("\n" + "-" * 70)
    if r_pearson < -0.3 and p_pearson < 0.05:
        print("✓ FRAMEWORK SUPPORTED: Significant negative correlation found!")
        print(f"  λ₁ and H are anti-correlated as predicted (r = {r_pearson:.3f})")
    elif r_pearson < 0 and p_pearson < 0.1:
        print("? SUGGESTIVE: Weak negative trend observed")
        print(f"  λ₁ and H show trend in predicted direction (r = {r_pearson:.3f})")
        print("  More data needed to confirm")
    elif abs(r_pearson) < 0.1:
        print("✗ INCONCLUSIVE: No significant correlation found")
        print(f"  λ₁ and H appear uncorrelated (r = {r_pearson:.3f})")
    else:
        print("✗ UNEXPECTED: Positive correlation found")
        print(f"  This contradicts the framework prediction")
    print("-" * 70)

    # =============================================================================
    # VISUALIZATION
    # =============================================================================

    print("\n4. Creating visualizations...")

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Panel 1: λ₁ vs H (THE CRITICAL TEST)
    ax1 = axes[0, 0]
    scatter = ax1.scatter(lambda1_arr, H_arr, c=delta_arr, cmap='coolwarm',
                         s=40, alpha=0.7, edgecolors='k', linewidth=0.5)
    ax1.axhline(H0_planck, color='blue', linestyle='--', label=f'H₀(Planck)={H0_planck}')
    ax1.axhline(73.0, color='red', linestyle='--', label='H₀(SH0ES)=73.0')

    # Fit line
    z = np.polyfit(lambda1_arr, H_arr, 1)
    p = np.poly1d(z)
    x_fit = np.linspace(lambda1_arr.min(), lambda1_arr.max(), 100)
    ax1.plot(x_fit, p(x_fit), 'k-', linewidth=2, label=f'Linear fit (r={r_pearson:.2f})')

    ax1.set_xlabel('Spectral Gap λ₁', fontsize=12)
    ax1.set_ylabel('Local Hubble Parameter H [km/s/Mpc]', fontsize=12)
    ax1.set_title('THE CRITICAL TEST: λ₁ vs H\n(CosmicFlows-4++ Real Data)', fontsize=14)
    ax1.legend(loc='upper right')
    plt.colorbar(scatter, ax=ax1, label='Mean δ')
    ax1.grid(True, alpha=0.3)

    # Panel 2: λ₁ vs density (control)
    ax2 = axes[0, 1]
    ax2.scatter(delta_arr, lambda1_arr, c=d_arr, cmap='viridis',
               s=40, alpha=0.7, edgecolors='k', linewidth=0.5)
    ax2.set_xlabel('Mean Density Contrast δ', fontsize=12)
    ax2.set_ylabel('Spectral Gap λ₁', fontsize=12)
    ax2.set_title(f'Control: λ₁ vs δ (r={r_delta:.2f})', fontsize=14)
    plt.colorbar(ax2.collections[0], ax=ax2, label='Distance [Mpc]')
    ax2.grid(True, alpha=0.3)

    # Panel 3: Density slice
    ax3 = axes[1, 0]
    slice_z = N // 2
    im = ax3.imshow(delta_mean[:, :, slice_z].T, origin='lower', cmap='coolwarm',
                    extent=[-L/2, L/2, -L/2, L/2], vmin=-1, vmax=2)
    ax3.set_xlabel('SGX [Mpc/h]', fontsize=12)
    ax3.set_ylabel('SGY [Mpc/h]', fontsize=12)
    ax3.set_title('CF4++ Density Contrast (z=0 slice)', fontsize=14)
    plt.colorbar(im, ax=ax3, label='δ = (ρ-ρ̄)/ρ̄')

    # Plot sample positions
    for r in results[:50]:
        sgx, sgy, sgz = r['position']
        if abs(sgz) < 50:  # Near z=0
            ax3.scatter(sgx, sgy, c='yellow', s=20, marker='x')

    # Panel 4: Summary
    ax4 = axes[1, 1]
    ax4.axis('off')

    summary = f"""
    SPECTRAL COSMOLOGY: REAL DATA TEST
    ══════════════════════════════════════════

    DATA: CosmicFlows-4++ (Courtois et al. 2025)
      Grid: 128³ cells, 1000 Mpc/h box
      Distance range: 20-400 Mpc
      Samples: {len(results)} valid regions

    PREDICTION:
      If dark energy = spectral gap, then:
      H ∝ 1/λ₁ → Corr(λ₁, H) < 0

    RESULT:
      Pearson r  = {r_pearson:+.3f} (p = {p_pearson:.2e})
      Spearman ρ = {r_spearman:+.3f} (p = {p_spearman:.2e})

    INTERPRETATION:
    """

    if r_pearson < -0.3 and p_pearson < 0.05:
        summary += "  ✓ SIGNIFICANT anti-correlation found!\n"
        summary += "  Framework prediction SUPPORTED"
    elif r_pearson < 0 and p_pearson < 0.1:
        summary += "  ? Weak negative trend observed\n"
        summary += "  Suggestive but needs more data"
    else:
        summary += f"  Correlation: {r_pearson:+.3f}\n"
        summary += "  Further investigation needed"

    ax4.text(0.05, 0.95, summary, transform=ax4.transAxes, fontsize=11,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

    plt.tight_layout()
    plt.savefig('lambda1_H_real_test.png', dpi=150, bbox_inches='tight')
    print("Saved: lambda1_H_real_test.png")

    # =============================================================================
    # ADDITIONAL ANALYSIS: By density environment
    # =============================================================================

    print("\n5. Analysis by density environment...")

    # Split into void-like (δ < 0) and dense (δ > 0) regions
    void_mask = delta_arr < -0.2
    dense_mask = delta_arr > 0.2

    if np.sum(void_mask) > 5 and np.sum(dense_mask) > 5:
        lambda1_void = lambda1_arr[void_mask]
        lambda1_dense = lambda1_arr[dense_mask]
        H_void = H_arr[void_mask]
        H_dense = H_arr[dense_mask]

        print(f"\nVoid-like regions (δ < -0.2): n = {np.sum(void_mask)}")
        print(f"  Mean λ₁: {np.mean(lambda1_void):.4f}")
        print(f"  Mean H:  {np.mean(H_void):.1f} km/s/Mpc")

        print(f"\nDense regions (δ > 0.2): n = {np.sum(dense_mask)}")
        print(f"  Mean λ₁: {np.mean(lambda1_dense):.4f}")
        print(f"  Mean H:  {np.mean(H_dense):.1f} km/s/Mpc")

        print(f"\nRatios:")
        print(f"  λ₁(dense)/λ₁(void) = {np.mean(lambda1_dense)/np.mean(lambda1_void):.2f}")
        print(f"  H(void)/H(dense)   = {np.mean(H_void)/np.mean(H_dense):.3f}")

        # This is the key prediction: voids should have lower λ₁ AND higher H
        if np.mean(lambda1_void) < np.mean(lambda1_dense) and np.mean(H_void) > np.mean(H_dense):
            print("\n✓ PREDICTED PATTERN: λ₁(void) < λ₁(dense) AND H(void) > H(dense)")
        else:
            print("\n? Pattern not as predicted")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
