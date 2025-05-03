import os
import json
import numpy as np
import pandas as pd
from tqdm import tqdm
from sklearn.decomposition import PCA, TruncatedSVD
from scipy import sparse
import matplotlib.pyplot as plt

# Directory containing the JSON files
DATA_DIR = os.path.dirname(__file__)

# Gather all JSON files
json_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json')]
print(f"Found {len(json_files)} JSON files.")

# --- Print table of all shapes (lengths of value arrays) ---

shapes = []
for fname in json_files:
    try:
        with open(os.path.join(DATA_DIR, fname)) as f:
            d = json.load(f)
            values = d.get("value", [])
            shapes.append({'file': fname, 'length': len(values)})
    except Exception as e:
        shapes.append({'file': fname, 'length': None})
        print(f"Error loading {fname}: {e}")
shapes_df = pd.DataFrame(shapes)
print("\nTable of all dataset shapes (length of 'value' arrays):")
print(shapes_df.sort_values('length', ascending=False).to_string(index=False))
print("\nSummary statistics for dataset lengths:")
print(shapes_df['length'].describe())

# Save the table as CSV
shapes_csv_path = os.path.join(DATA_DIR, 'dataset_shapes.csv')
shapes_df.to_csv(shapes_csv_path, index=False)
print(f"\nSaved dataset shapes table to {shapes_csv_path}")
# ... existing code ...
shapes = []
for fname in json_files:
    try:
        with open(os.path.join(DATA_DIR, fname)) as f:
            d = json.load(f)
            values = d.get("value", [])
            # Infer dtype
            non_nulls = [v for v in values if v is not None]
            if not non_nulls:
                dtype = 'empty'
            else:
                types = set(type(v).__name__ for v in non_nulls)
                if len(types) == 1:
                    dtype = list(types)[0]
                else:
                    dtype = 'mixed'
            shapes.append({'file': fname, 'length': len(values), 'dtype': dtype})
    except Exception as e:
        shapes.append({'file': fname, 'length': None, 'dtype': 'error'})
        print(f"Error loading {fname}: {e}")
shapes_df = pd.DataFrame(shapes)
print("\nTable of all dataset shapes (length and dtype of 'value' arrays):")
print(shapes_df.sort_values('length', ascending=False).to_string(index=False))
print("\nSummary statistics for dataset lengths:")
print(shapes_df['length'].describe())
print("\nData type counts:")
print(shapes_df['dtype'].value_counts())

# Save the table as CSV
shapes_csv_path = os.path.join(DATA_DIR, 'dataset_shapes.csv')
shapes_df.to_csv(shapes_csv_path, index=False)
print(f"\nSaved dataset shapes table to {shapes_csv_path}")
# ... existing code ...

all_data = {}

# Load data with progress bar
tqdm_files = tqdm(json_files, desc='Loading JSON files')
for fname in tqdm_files:
    try:
        with open(os.path.join(DATA_DIR, fname)) as f:
            d = json.load(f)
            values = d.get("value", [])
            all_data[fname] = values
    except Exception as e:
        print(f"Error loading {fname}: {e}")

# Convert to DataFrame (columns: files, rows: value index)
df = pd.DataFrame.from_dict(all_data, orient="index").transpose()
print(f"DataFrame shape: {df.shape}")
print(df.head())

# --- Enhanced missingness analysis ---
missing_per_col = df.isna().sum()
missing_per_row = df.isna().sum(axis=1)
print("\nMissing values per column (top 10):")
print(missing_per_col.sort_values(ascending=False).head(10))
print("\nMissing values per row (top 10):")
print(missing_per_row.sort_values(ascending=False).head(10))
print(f"\nTotal missing values: {df.isna().sum().sum()} / {df.size} ({100*df.isna().sum().sum()/df.size:.2f}%)")

# --- Impute missing data ---
def impute_col(col):
    # If all values are NaN, fill with 0; else fill with mean
    if col.isna().all():
        return col.fillna(0)
    else:
        return col.fillna(col.mean())
df = df.apply(impute_col, axis=0)
print(f"NaN count after imputation: {df.isna().sum().sum()}")

# --- Dimensionality reduction ---
# Always use TruncatedSVD for interpretability and sparse support
X_sparse = sparse.csr_matrix(df.values)
print(f"Sparse matrix shape: {X_sparse.shape}, nnz: {X_sparse.nnz}")
svd = TruncatedSVD(n_components=3, random_state=42)
X_3d = svd.fit_transform(X_sparse)
explained = svd.explained_variance_ratio_
print("Explained variance ratio:", explained)

# --- Feature contribution analysis ---
feature_names = df.columns.to_numpy()
components = svd.components_  # shape: (3, n_features)
top_features = []
for i, comp in enumerate(components):
    abs_comp = np.abs(comp)
    top_idx = abs_comp.argsort()[::-1][:5]
    top = [(feature_names[j], comp[j]) for j in top_idx]
    top_features.append(top)
    print(f"\nTop contributing features for Component {i+1}:")
    for name, val in top:
        print(f"  {name}: {val:.4f}")

# --- Color coding: by mean value of a selected feature (first feature as example) ---
color_feature = feature_names[0]
color_vals = df[color_feature].values

# --- 3D scatter plot ---
fig = plt.figure(figsize=(14, 9))
ax = fig.add_subplot(111, projection='3d')
sc = ax.scatter(X_3d[:, 0], X_3d[:, 1], X_3d[:, 2], c=color_vals, cmap='viridis', alpha=0.7)
ax.set_xlabel('Component 1')
ax.set_ylabel('Component 2')
ax.set_zlabel('Component 3')
plt.title(f'3D SVD Reduction of asub_data (color: {color_feature})\nExplained variance: {explained[0]:.2%}, {explained[1]:.2%}, {explained[2]:.2%}')
cbar = plt.colorbar(sc, label=f'{color_feature} value')
plt.tight_layout()

# Save and show
plot_path = os.path.join(DATA_DIR, f'asub_data_3d_svd_enhanced.png')
plt.savefig(plot_path)
print(f"Plot saved to {plot_path}")
plt.show()

# --- Summary of what the reduction shows ---
print("\n--- Dimensionality Reduction Summary ---")
print(f"Method: TruncatedSVD (sparse, all data imputed)")
print(f"Shape: {X_3d.shape}")
print(f"Explained variance ratio: {explained}")
for i, top in enumerate(top_features):
    print(f"Component {i+1} is most influenced by:")
    for name, val in top:
        print(f"  {name} (weight: {val:.4f})")
print(f"\nColor in plot represents: {color_feature}")
print("Interpretation: Points close together in 3D space have similar values across all statistics. The axes (components) are linear combinations of the original statistics, with the above features contributing most to each axis. Outliers or clusters may indicate interesting patterns or anomalies in the data.") 