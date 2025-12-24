"""
Generate publication-quality figures for SafeOps-LogMiner paper.

Outputs:
- figures/feature_importance.pdf
- figures/confusion_matrix.pdf
"""

import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Set publication style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({
    'font.size': 11,
    'font.family': 'serif',
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1
})

# Create figures directory
figures_dir = Path(__file__).parent.parent / 'figures'
figures_dir.mkdir(exist_ok=True)

# Load evaluation results
data_path = Path(__file__).parent.parent / 'data' / 'evaluation_results.json'
with open(data_path) as f:
    results = json.load(f)


def plot_feature_importance():
    """
    Create horizontal bar chart showing feature importance.
    Shows both permutation importance and ablation study results.
    """
    perm_importance = results['feature_analysis']['permutation_importance']
    ablation = results['feature_analysis']['ablation_study']
    
    # Sort features by permutation importance
    sorted_features = sorted(perm_importance.items(), key=lambda x: x[1], reverse=True)
    features = [f[0] for f in sorted_features]
    perm_values = [f[1] for f in sorted_features]
    ablation_values = [ablation[f]['delta_from_baseline'] for f in features]
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
    
    # Color based on positive/negative
    colors_perm = ['#2ecc71' if v >= 0 else '#e74c3c' for v in perm_values]
    colors_abl = ['#e74c3c' if v <= 0 else '#2ecc71' for v in ablation_values]
    
    # Plot 1: Permutation Importance
    y_pos = np.arange(len(features))
    ax1.barh(y_pos, perm_values, color=colors_perm, edgecolor='black', linewidth=0.5)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([f.replace('_', '\n') for f in features], fontsize=9)
    ax1.set_xlabel('ΔF1 Score (when feature permuted)')
    ax1.set_title('(a) Permutation Importance')
    ax1.axvline(x=0, color='black', linewidth=0.8, linestyle='-')
    ax1.set_xlim(-0.12, 0.10)
    
    # Add value labels
    for i, v in enumerate(perm_values):
        ax1.text(v + 0.003 if v >= 0 else v - 0.003, i, f'{v:+.3f}', 
                va='center', ha='left' if v >= 0 else 'right', fontsize=8)
    
    # Plot 2: Ablation Study
    ax2.barh(y_pos, ablation_values, color=colors_abl, edgecolor='black', linewidth=0.5)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([f.replace('_', '\n') for f in features], fontsize=9)
    ax2.set_xlabel('ΔF1 Score (when feature removed)')
    ax2.set_title('(b) Ablation Study')
    ax2.axvline(x=0, color='black', linewidth=0.8, linestyle='-')
    ax2.set_xlim(-0.08, 0.06)
    
    # Add value labels
    for i, v in enumerate(ablation_values):
        ax2.text(v + 0.003 if v >= 0 else v - 0.003, i, f'{v:+.3f}', 
                va='center', ha='left' if v >= 0 else 'right', fontsize=8)
    
    plt.tight_layout()
    
    # Save
    output_path = figures_dir / 'feature_importance.pdf'
    plt.savefig(output_path)
    plt.savefig(figures_dir / 'feature_importance.png')
    print(f"Saved: {output_path}")
    plt.close()


def plot_confusion_matrix():
    """
    Create confusion matrix heatmaps for all baseline models.
    """
    models = ['IsolationForest', 'OneClassSVM', 'LOF', 'Threshold']
    display_names = ['Isolation Forest', 'One-Class SVM', 'LOF', 'Threshold-based']
    
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    axes = axes.flatten()
    
    for idx, (model, display_name) in enumerate(zip(models, display_names)):
        ax = axes[idx]
        cm = np.array(results['baseline_comparison'][model]['confusion_matrix'])
        
        # Calculate percentages
        cm_percent = cm.astype('float') / cm.sum() * 100
        
        # Create annotation labels with both count and percentage
        annot = np.array([[f'{cm[i,j]}\n({cm_percent[i,j]:.1f}%)' 
                          for j in range(2)] for i in range(2)])
        
        # Plot heatmap
        sns.heatmap(cm, annot=annot, fmt='', cmap='Blues', ax=ax,
                   xticklabels=['Normal', 'Anomaly'],
                   yticklabels=['Normal', 'Anomaly'],
                   cbar=False, annot_kws={'size': 11})
        
        ax.set_xlabel('Predicted Label')
        ax.set_ylabel('True Label')
        
        # Add metrics to title
        metrics = results['baseline_comparison'][model]
        ax.set_title(f'{display_name}\nF1={metrics["f1"]:.3f}, Prec={metrics["precision"]:.3f}, Rec={metrics["recall"]:.3f}')
    
    plt.tight_layout()
    
    # Save
    output_path = figures_dir / 'confusion_matrix.pdf'
    plt.savefig(output_path)
    plt.savefig(figures_dir / 'confusion_matrix.png')
    print(f"Saved: {output_path}")
    plt.close()


def plot_single_confusion_matrix():
    """
    Create a single confusion matrix for Isolation Forest (primary model).
    """
    fig, ax = plt.subplots(figsize=(6, 5))
    
    cm = np.array(results['baseline_comparison']['IsolationForest']['confusion_matrix'])
    metrics = results['baseline_comparison']['IsolationForest']
    
    # Calculate percentages
    cm_percent = cm.astype('float') / cm.sum() * 100
    
    # Create annotation labels
    labels = np.array([
        [f'TN\n{cm[0,0]}\n({cm_percent[0,0]:.1f}%)', f'FP\n{cm[0,1]}\n({cm_percent[0,1]:.1f}%)'],
        [f'FN\n{cm[1,0]}\n({cm_percent[1,0]:.1f}%)', f'TP\n{cm[1,1]}\n({cm_percent[1,1]:.1f}%)']
    ])
    
    # Plot heatmap
    sns.heatmap(cm, annot=labels, fmt='', cmap='Blues', ax=ax,
               xticklabels=['Predicted\nNormal', 'Predicted\nAnomaly'],
               yticklabels=['Actual\nNormal', 'Actual\nAnomaly'],
               cbar=True, annot_kws={'size': 12, 'weight': 'bold'})
    
    ax.set_title(f'Isolation Forest Confusion Matrix\n'
                f'Accuracy={metrics["accuracy"]:.3f}, F1={metrics["f1"]:.3f}, '
                f'FPR={metrics["false_positive_rate"]:.3f}',
                fontsize=12)
    
    plt.tight_layout()
    
    # Save
    output_path = figures_dir / 'confusion_matrix_if.pdf'
    plt.savefig(output_path)
    plt.savefig(figures_dir / 'confusion_matrix_if.png')
    print(f"Saved: {output_path}")
    plt.close()


if __name__ == '__main__':
    print("Generating figures for SafeOps-LogMiner paper...")
    print(f"Output directory: {figures_dir}")
    print()
    
    plot_feature_importance()
    plot_confusion_matrix()
    plot_single_confusion_matrix()
    
    print()
    print("All figures generated successfully!")
