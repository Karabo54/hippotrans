import csv
import os

class Fuel60BCalculator:
    def __init__(self, csv_filepath=None):
        self.matrix = {}
        self.available_densities = []
        if csv_filepath and os.path.exists(csv_filepath):
            self.load_matrix(csv_filepath)

    def load_matrix(self, filepath):
        """Parses the 60B structural matrix from scratch."""
        try:
            with open(filepath, mode='r', encoding='utf-8') as f:
                reader = list(csv.reader(f))
            
            header_row_idx = None
            for idx, row in enumerate(reader):
                if row and any(token in row for token in ['Temp', 'Density']):
                    header_row_idx = idx
                    break
            
            if header_row_idx is None:
                return

            # Column headers starting at index 2 (e.g., 0.7, 0.705, 0.71...)
            headers = [h.strip() for h in reader[header_row_idx]]
            density_columns = {}
            
            for col_idx, h_val in enumerate(headers):
                if col_idx >= 2 and h_val:
                    try:
                        d_float = float(h_val)
                        density_columns[col_idx] = d_float
                        self.available_densities.append(d_float)
                    except ValueError:
                        continue
            
            # Map out each individual temperature row entry
            for row in reader[header_row_idx + 1:]:
                if not row or not row[0].strip():
                    continue
                try:
                    temp_val = float(row[0].strip())
                    temp_key = f"{temp_val:.2f}" # Keep precision for 0.25 increment steps
                    
                    self.matrix[temp_key] = {}
                    for col_idx, d_float in density_columns.items():
                        if col_idx < len(row) and row[col_idx].strip():
                            self.matrix[temp_key][d_float] = float(row[col_idx].strip())
                except ValueError:
                    continue
                    
            self.available_densities = sorted(list(set(self.available_densities)))
        except Exception as e:
            print(f"Error initializing 60B Fuel Matrix: {e}")

    def get_vcf(self, temperature, density):
        """Looks up correction values using closest match algorithm."""
        if not self.matrix:
            return 1.0

        # Step 1: Match closest available temperature row
        target_temp = float(temperature)
        available_temps = [float(t) for t in self.matrix.keys()]
        closest_temp = min(available_temps, key=lambda x: abs(x - target_temp))
        
        # Guard rail logic for bounds
        if abs(closest_temp - target_temp) > 2.0:
            return 1.0
            
        temp_key = f"{closest_temp:.2f}"
        row_mappings = self.matrix.get(temp_key, {})

        # Step 2: Match closest available density column
        target_density = float(density)
        closest_density = min(row_mappings.keys(), key=lambda x: abs(x - target_density))
        
        if abs(closest_density - target_density) > 0.05:
            return 1.0

        return row_mappings.get(closest_density, 1.0)

    def calculate(self, gross_volume, temperature, density):
        """Returns the fully parsed fuel metric dataset."""
        gross = float(gross_volume)
        vcf = self.get_vcf(temperature, density)
        
        net_volume = gross * vcf
        loss_gain = gross - net_volume
        pct = (loss_gain / gross * 100) if gross else 0.0

        return {
            "vcf": round(vcf, 4),
            "net_volume": round(net_volume, 2),
            "loss_gain": round(loss_gain, 2),
            "percentage": round(pct, 4),
            "is_loss": loss_gain > 0
        }