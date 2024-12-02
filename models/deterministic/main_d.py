import pandas as pd

from pyomo.opt import SolverFactory
from pyomo.environ import *
from pyomo.network import *
from datetime import datetime

import assets.chp_d as chp
import assets.boiler_d as boiler
import assets.heat_storage_d as heat_storage
import assets.grid_d as grid

import json
import os
import re
import glob

# Load the config.json
with open('../config.json', 'r') as f:
    config = json.load(f)

# Model Config
model_type = 'deterministic'
model_config = config['deterministic']

# Global Config
global_config = config['global']

# Paths
data_path = global_config['data_path']

# Declare paths
PATH_IN = os.path.join(data_path, model_config['input_path'])
PATH_OUT = os.path.join(data_path, model_config['output_path'])
PATH_OUT_LOGS = os.path.join(data_path, model_config['log_path'])
PATH_OUT_TIMESERIES = os.path.join(data_path, model_config['timeseries_path'])
PATH_OUT_OBJECTIVES = os.path.join(data_path, model_config['objectives_path'])
PATH_OUT_ACTUAL = os.path.join(data_path, model_config['actual_path'])
PATH_OUT_SCENARIOS = os.path.join(data_path, model_config['scenarios_path'])

# Heat Demand Data
FILE_HEAT_DEMAND = global_config['heat_demand_file']
FILE_HEAT_DEMAND_SCENARIOS = global_config['heat_demand_scenario_file']

# Weighted Heat Demand
WEIGHTED_HEAT_DEMAND = global_config['weighted_heat_demand']

# Declare constants
GAS_PRICE = global_config['gas_price']  # €/kWh  (HS)
POWER_PRICE = global_config['power_price']  # €/kWh (el)
HEAT_PRICE = global_config['heat_price']  # €/kWh (th)
CALORIFIC_VALUE_NGAS = global_config['calorific_value_ngas']  # kWh/m3

# CHP
CHP_BONUS_SELF_CONSUMPTION = global_config['chp_bonus_self_consumption']  # €/kWhel
CHP_BONUS = global_config['chp_bonus']  # €/kWhel
CHP_INDEX_EEX = global_config['chp_index_eex']  # €/kWhel
ENERGY_TAX_REFUND_GAS = global_config['energy_tax_refund_gas']  # €/kWhHS
AVOIDED_GRID_FEES = global_config['avoided_grid_fees']  # €/kWhel
SHARE_SELF_CONSUMPTION = global_config['share_self_consumption']  # %
SHARE_FEED_IN = global_config['share_feed_in']  # %

# Boiler
POWERCOST_TO_HEAT_SALES_RATIO = global_config['power_cost_to_heat_sales_ratio']

# Heat Storage
COST_CHARGE = global_config['cost_charge']  # €/kWh
COST_DISCHARGE = global_config['cost_discharge']  # €/kWh

# Costs
MAINTENANCE_COSTS = global_config['maintenance_cost']  # €/kWh (HS)


class Model:
    """Model class."""

    def __init__(self, heat_demand_data):
        self.model = AbstractModel()
        self.instance = None
        self.solver = None
        self.timeseries_data = None
        self.results = None
        self.results_data = None
        self.USE_WEIGHTED_HEAT_DEMAND = Model.USE_WEIGHTED_HEAT_DEMAND
        self._load_timeseries_data(heat_demand_data)
        self.objective_value = None  # Hinzugefügt: Variable zum Speichern des Zielfunktionswerts

    def set_solver(self, solver_name, **kwargs):
        self.solver = SolverFactory(solver_name)

        for key in kwargs:
            self.solver.options[key] = kwargs[key]

    def _load_timeseries_data(self, heat_demand_data):
        # heat_demand_data: Dictionary mit Heat Demand Daten
        t_values = list(map(int, heat_demand_data.keys()))
        heat_demand = {int(k): v for k, v in heat_demand_data.items()}

        self.timeseries_data = {None: {
            't': {None: t_values},
            'heat_demand': heat_demand
        }}

    def add_components(self):
        """Add components to the model."""

        # Sets
        self.model.t = Set(ordered=True)

        # Parameters
        self.model.GAS_PRICE = Param(initialize=GAS_PRICE)
        self.model.POWER_PRICE = Param(initialize=POWER_PRICE)
        self.model.HEAT_PRICE = Param(initialize=HEAT_PRICE)
        self.model.heat_demand = Param(self.model.t)

        # Assets

        chp1 = chp.Chp(
            'chp1', PATH_IN + '/assets/chp_operation_1.csv'
        )
        chp2 = chp.Chp(
            'chp2', PATH_IN + '/assets/chp_operation_2.csv'
        )

        boiler1 = boiler.Boiler(
            'boiler1', PATH_IN + '/assets/boiler_operation.csv'
        )

        heat_storage1 = heat_storage.HeatStorage(
            'heat_storage1', PATH_IN + '/assets/heat_storage.csv'
        )

        ngas_grid = grid.NGasGrid('ngas_grid')

        power_grid = grid.ElectricalGrid(
            'power_grid', PATH_IN + '/assets/power_grid.csv'
        )

        heat_grid = grid.HeatGrid(
            'heat_grid', PATH_IN + '/assets/heat_grid.csv'
        )

        chp1.add_to_model(self.model)
        chp2.add_to_model(self.model)
        boiler1.add_to_model(self.model)
        heat_storage1.add_to_model(self.model)
        ngas_grid.add_to_model(self.model)
        power_grid.add_to_model(self.model)
        heat_grid.add_to_model(self.model)

    def add_objective(self):
        """Add objective function to model."""
        self.model.objective = Objective(
            rule=self.objective_expr,
            sense=minimize
        )

    def instantiate_model(self):
        """Create a concrete instance of the model."""
        self.instance = self.model.create_instance(self.timeseries_data)

    def expand_arcs(self):
        """Expands arcs and generate connection constraints."""
        TransformationFactory('network.expand_arcs').apply_to(self.instance)

    def add_instance_components(self, component_name, component):
        """Add components to the instance."""
        self.instance.add_component(component_name, component)

    def add_arcs(self):
        """Add arcs to the instance."""

        self.instance.arc01 = Arc(
            source=self.instance.chp1.power_out,
            destination=self.instance.power_grid.power_in
        )
        # New
        self.instance.arc02 = Arc(
            source=self.instance.chp2.power_out,
            destination=self.instance.power_grid.power_in
        )
        # Updated
        self.instance.arc03 = Arc(
            source=self.instance.chp1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        # New
        self.instance.arc04 = Arc(
            source=self.instance.chp2.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc05 = Arc(
            source=self.instance.boiler1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        self.instance.arc06 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.boiler1.gas_in
        )
        self.instance.arc07 = Arc(
            source=self.instance.ngas_grid.gas_out,
            destination=self.instance.chp1.gas_in
        )
        # New
        self.instance.arc08 = Arc(
            source=self.instance.heat_storage1.heat_out,
            destination=self.instance.heat_grid.heat_in
        )
        # New
        self.instance.arc09 = Arc(
            source=self.instance.heat_grid.heat_out,
            destination=self.instance.heat_storage1.heat_in
        )

    def solve(self):
        """Solve the model."""
        self.results = self.solver.solve(
            self.instance,
            symbolic_solver_labels=True,
            tee=True,
            load_solutions=True,
            report_timing=True,
        )
        # Nach dem Lösen des Modells den Zielfunktionswert speichern
        self.objective_value = value(self.instance.objective)

    def write_results(self):
        """Write results to file."""
        self.results.write()

        df_params = pd.DataFrame()
        df_variables = pd.DataFrame()
        df_output = pd.DataFrame()

        for params in self.instance.component_objects(Param, active=True):
            name = params.name
            if len(params) == 1:
                single_value = value(list(params.values())[0])
                df_params[name] = [single_value for t in self.instance.t]
            else:
                df_params[name] = [value(params[t]) for t in self.instance.t]

        for variables in self.instance.component_objects(Var, active=True):
            name = variables.name
            df_variables[name] = [value(variables[t]) for t in self.instance.t]

        df_output = pd.concat([df_params, df_variables], axis=1)
        df_output.index = self.instance.t
        df_output.index.name = 't'

        self.results_data = df_output

    def save_results(self, filepath):
        """Save results to object."""
        self.results_data.to_csv(filepath)

    def objective_expr(self, model):
        """Objective function expression."""
        objective_expr = (
            self._gas_costs(model) +
            self._power_costs(model) +
            self._storage_costs(model) +
            self._maintenance_costs(model) -
            self._power_revenue(model) -
            self._heat_revenue(model) -
            self._chp_revenue(model)
        )
        return objective_expr

    def _gas_costs(self, model):
        """ Calculate gas costs for CHP and Boiler."""
        gas_costs = (
            quicksum(model.chp1.gas[t] * model.GAS_PRICE for t in model.t) +
            quicksum(model.chp2.gas[t] * model.GAS_PRICE for t in model.t) +
            quicksum(model.boiler1.gas[t] * model.GAS_PRICE for t in model.t)
        )
        return gas_costs

    def _power_costs(self, model):
        """Calculate power costs for Boiler."""
        power_costs = quicksum(model.boiler1.heat[t] * POWERCOST_TO_HEAT_SALES_RATIO * model.POWER_PRICE for t in model.t)
        return power_costs

    # New
    def _storage_costs(self, model):
        """Calculate storage costs for Heat Storage."""
        storage_costs = (
            quicksum(model.heat_storage1.heat_charge[t] * COST_CHARGE for t in model.t) +
            quicksum(model.heat_storage1.heat_discharge[t] * COST_DISCHARGE for t in model.t)
        )
        return storage_costs

    def _maintenance_costs(self, model):
        """Calculate maintenance costs for CHP."""
        maintenance_costs = (
            quicksum(model.chp1.bin[t] * MAINTENANCE_COSTS for t in model.t) +
            quicksum(model.chp2.bin[t] * MAINTENANCE_COSTS for t in model.t)
        )
        return maintenance_costs

    def _power_revenue(self, model):
        """Calculate power revenue for CHP."""
        power_revenue = (
            quicksum(model.chp1.power[t] * model.POWER_PRICE for t in model.t) +
            quicksum(model.chp2.power[t] * model.POWER_PRICE for t in model.t)
        )
        return power_revenue

    def _heat_revenue(self, model):
        """Calculate heat revenue for CHP and Boiler."""
        heat_revenue = (
            quicksum(model.chp1.heat[t] * model.HEAT_PRICE for t in model.t) +
            quicksum(model.chp2.heat[t] * model.HEAT_PRICE for t in model.t) +
            quicksum(model.boiler1.heat[t] * model.HEAT_PRICE for t in model.t)
        )
        return heat_revenue

    def _chp_revenue(self, model):
        """Calculate CHP revenue."""
        chp_bonus_for_self_consumption = (
            quicksum(model.chp1.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t) +
            quicksum(model.chp2.power[t] * CHP_BONUS_SELF_CONSUMPTION * SHARE_SELF_CONSUMPTION for t in model.t)
        )

        chp_bonus_for_feed_in = (
            quicksum(model.chp1.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t) +
            quicksum(model.chp2.power[t] * CHP_BONUS * SHARE_FEED_IN for t in model.t)
        )

        chp_index = (
            quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t) +
            quicksum((model.chp2.power[t] - model.chp2.power[t] * SHARE_SELF_CONSUMPTION) * CHP_INDEX_EEX for t in model.t)
        )

        avoided_grid_fees = (
            quicksum((model.chp1.power[t] - model.chp1.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t) +
            quicksum((model.chp2.power[t] - model.chp2.power[t] * SHARE_SELF_CONSUMPTION) * AVOIDED_GRID_FEES for t in model.t)
        )

        energy_tax_refund = (
            quicksum(model.chp1.gas[t] * ENERGY_TAX_REFUND_GAS for t in model.t) +
            quicksum(model.chp2.gas[t] * ENERGY_TAX_REFUND_GAS for t in model.t)
        )

        chp_revenue = (
            chp_bonus_for_self_consumption +
            chp_bonus_for_feed_in +
            chp_index +
            avoided_grid_fees +
            energy_tax_refund
        )
        return chp_revenue


    def _extract_scenario_info(self, file):
        """Extract the start date, end date, and period from the file name."""
        base_name = os.path.basename(file)
        
        # Muster für Dateien, die mit 'heat_demand_' beginnen
        pattern1 = r'heat_demand_(\d{8})_to_(\d{8})_(\w+)\.json$'
        match1 = re.match(pattern1, base_name)
        if match1:
            start_date = match1.group(1)
            end_date = match1.group(2)
            period = match1.group(3)
            return start_date, end_date, period
        
        # Muster für Dateien, die mit 'weighted_heat_demand_' beginnen
        pattern2 = r'weighted_heat_demand_(\d{8})\.json$'
        match2 = re.match(pattern2, base_name)
        if match2:
            start_date = match2.group(1)
            end_date = match2.group(1)  # Kein Enddatum in diesem Dateinamen
            period = 'day'    # Kein Zeitraum in diesem Dateinamen
            return start_date, end_date, period
        
        # Muster für Dateien, die mit 'reduced_heat_demand_scenarios_' beginnen
        pattern3 = r'reduced_heat_demand_scenarios_(\d{8})_to_(\d{8})_(\w+)\.json$'
        match3 = re.match(pattern3, base_name)
        if match3:
            start_date = match3.group(1)
            end_date = match3.group(2)
            period = match3.group(3)
            return start_date, end_date, period
    
    
        # Muster für Dateien, die mit 'actual_heat_demand_' beginnen
        pattern4 = r'actual_heat_demand_(\d{8})_to_(\d{8})_(\w+)\.json$'
        match4 = re.match(pattern4, base_name)
        if match4:
            start_date = match4.group(1)
            end_date = match4.group(2)
            period = match4.group(3)
            return start_date, end_date, period
        
        # Falls kein Muster passt, None zurückgeben
        return None, None, None


if __name__ == "__main__":
    # Flag zum Steuern, ob mehrere Szenarien durchlaufen werden sollen
    
    run_actual_heat_demand = False 
    run_multiple_scenarios = False # Setzen Sie diesen Wert auf False, um nur ein Szenario zu laufen
    Model.USE_WEIGHTED_HEAT_DEMAND = True

    # Einheitliche Solver-Einstellungen
    solver_name = 'gurobi'
    solver_options = {
        'MIPGap': 0.01,
        'TimeLimit': 1000,
    }

    if run_multiple_scenarios:
        # Pfad zu den Szenario-Dateien
        scenario_files = glob.glob(f'{PATH_IN}demands/reduced_heat_demand_scenarios_*.json')

        # Liste zur Speicherung aller Zielfunktionswerte
        all_objective_values = []

        # Iteration über alle Szenario-Dateien
        for scenario_file in scenario_files:
            # Laden der Heat-Demand-Szenarien aus der aktuellen Datei
            with open(scenario_file) as f:
                heat_demand_scenarios = json.load(f)

            # Entfernen der "Probability" Einträge aus den Szenarien
            for scenario in heat_demand_scenarios:
                if 'Probability' in heat_demand_scenarios[scenario]:
                    del heat_demand_scenarios[scenario]['Probability']

            # Extrahieren von Startdatum, Enddatum und Zeitraum aus dem Dateinamen
            dummy_model = Model({})
            start_date, end_date, period = dummy_model._extract_scenario_info(scenario_file)

            # Liste zur Speicherung der Zielfunktionswerte für die aktuelle Datei
            objective_values = []

            # Iteration über alle Szenarien in der aktuellen Datei
            for scenario_name, heat_demand_data in heat_demand_scenarios.items():
                print(f'\n### Running scenario: {scenario_name} from file: {os.path.basename(scenario_file)} ###\n')

                model = Model(heat_demand_data)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_filename = f"{PATH_OUT_LOGS}logfile_{timestamp}_{start_date}_{period}_{scenario_name}.log"

                print('Setting solver...')
                # Verwendung der einheitlichen Solver-Einstellungen
                solver_options_with_log = solver_options.copy()
                solver_options_with_log['LogFile'] = log_filename
                model.set_solver(
                    solver_name=solver_name,
                    **solver_options_with_log
                )

                print('Adding components...')
                model.add_components()

                print('Adding objective...')
                model.add_objective()

                print('Instantiating model...')
                model.instantiate_model()

                print('Declaring arcs...')
                model.add_arcs()
                model.expand_arcs()

                print('Solving model...')
                model.solve()

                # Zielfunktionswert speichern
                objective_value = model.objective_value
                objective_values.append({'Scenario': scenario_name, 'ObjectiveValue': objective_value})

                print('Writing results...')
                model.write_results()

                # Speichern der Ergebnisse mit Szenarioname und Dateiname im Dateinamen
                output_file = f'd_{start_date}_to_{end_date}_{period}_{scenario_name}_ts.csv'
                model.save_results(PATH_OUT_SCENARIOS + output_file)

            # Speichern der Zielfunktionswerte für die aktuelle Datei
            df_objectives = pd.DataFrame(objective_values)
            objectives_file = f'{PATH_OUT_SCENARIOS}d_scenarios_{start_date}_to_{end_date}_{period}_obj.csv'
            df_objectives.to_csv(objectives_file, index=False)
            
            print(f'\n### Scenario file {start_date} have been processed  ###')

        #     # Hinzufügen der Ergebnisse zur Gesamtliste
        #     all_objective_values.extend(objective_values)

        # # Optional: Speichern aller Zielfunktionswerte in einer Gesamtdatei
        # df_all_objectives = pd.DataFrame(all_objective_values)
        # all_objectives_file = f'{PATH_OUT_SCENARIOS}d_all_scenarios_objectives.csv'
        # df_all_objectives.to_csv(all_objectives_file, index=False)

    else:

        if Model.USE_WEIGHTED_HEAT_DEMAND:
            heat_demand_files = glob.glob(f'{PATH_IN}demands/weighted_heat_demand/weighted_heat_demand_*.json')
            prefix = 'weighted_'
        else:
            #heat_demand_file = FILE_HEAT_DEMAND
            heat_demand_files = glob.glob(f'{PATH_IN}demands/heat_demand_*.json')
            prefix = ''
        
          # Iteration über alle Heat-Demand-Dateien
        for heat_demand_file in heat_demand_files:
            # Laden des Heat Demands aus der Datei
            with open(heat_demand_file) as f:
                heat_demand_data = json.load(f)


            # # Laden des Heat Demands aus der ursprünglichen Datei
            # with open(f'{PATH_IN}demands/{heat_demand_file}') as f:
            #     heat_demand_data = json.load(f)

            # Falls die Daten in einem speziellen Format vorliegen (z.B. unter 'heat_demand'), anpassen
            if 'heat_demand' in heat_demand_data:
                heat_demand_data = heat_demand_data['heat_demand']

            model = Model(heat_demand_data)

            start_date, end_date, period = model._extract_scenario_info(heat_demand_file)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"{PATH_OUT_LOGS}{prefix}logfile_{timestamp}_{start_date}_{period}.log"

            print('Setting solver...')
            # Verwendung der einheitlichen Solver-Einstellungen
            solver_options_with_log = solver_options.copy()
            solver_options_with_log['LogFile'] = log_filename
            model.set_solver(
                solver_name=solver_name,
                **solver_options_with_log
            )

            print('Adding components...')
            model.add_components()

            print('Adding objective...')
            model.add_objective()

            print('Instantiating model...')
            model.instantiate_model()

            print('Declaring arcs...')
            model.add_arcs()
            model.expand_arcs()

            print('Solving model...')
            model.solve()

            # Save the objective value to a CSV file
            objective_value = model.objective_value
            df_objective = pd.DataFrame([{'ObjectiveValue': objective_value}])
            objectives_file = f'{PATH_OUT_OBJECTIVES}d_{prefix}{start_date}_to_{end_date}_{period}_obj.csv'
            df_objective.to_csv(objectives_file, index=False)

            print('Writing results...')
            model.write_results()

            # Speichern der Ergebnisse
            output_file = f'd_{prefix}{start_date}_to_{end_date}_{period}_ts.csv'
            model.save_results(PATH_OUT_TIMESERIES + output_file)

            print('\n### Single scenario has been processed. ###')

    # Erweiterung: Optimieren des tatsächlichen Heat Demands
    if run_actual_heat_demand:
        # Pfad zu den tatsächlichen Heat-Demand-Dateien
        actual_heat_demand_files = glob.glob(f'{PATH_IN}demands/actual_heat_demand_*.json')
            
        # Iteration über alle tatsächlichen Heat-Demand-Dateien
        for actual_heat_demand_file in actual_heat_demand_files:
            # Laden des tatsächlichen Heat Demands aus der entsprechenden Datei
            with open(actual_heat_demand_file) as f:
                actual_heat_demand_data = json.load(f)

            if 'heat_demand' in actual_heat_demand_data:
                 actual_heat_demand_data = actual_heat_demand_data['heat_demand']

            actual_model = Model(actual_heat_demand_data)

            # Extrahieren von Startdatum, Enddatum und Zeitraum
            start_date_actual, end_date_actual, period_actual = actual_model._extract_scenario_info(actual_heat_demand_file)

            # Überprüfen, ob die Extraktion erfolgreich war
            if start_date_actual is None:
                print(f"Warnung: Konnte Startdatum nicht aus dem Dateinamen {actual_heat_demand_file} extrahieren.")
                continue  # Überspringen dieser Datei oder entsprechend behandeln

            timestamp_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename_actual = f"{PATH_OUT_LOGS}logfile_actual_{timestamp_actual}_{start_date_actual}_{period_actual}.log"

            print('Setting solver for actual heat demand...')
            # Verwendung der einheitlichen Solver-Einstellungen
            solver_options_with_log = solver_options.copy()
            solver_options_with_log['LogFile'] = log_filename_actual
            actual_model.set_solver(
                solver_name=solver_name,
                **solver_options_with_log
            )

            print('Adding components...')
            actual_model.add_components()

            print('Adding objective...')
            actual_model.add_objective()

            print('Instantiating model...')
            actual_model.instantiate_model()

            print('Declaring arcs...')
            actual_model.add_arcs()
            actual_model.expand_arcs()

            print('Solving model...')
            actual_model.solve()

            print('Writing results...')
            actual_model.write_results()

            # Speichern der Ergebnisse
            output_file_actual = f'd_actual_{start_date_actual}_to_{end_date_actual}_{period_actual}_ts.csv'
            actual_model.save_results(PATH_OUT_ACTUAL + output_file_actual)

            # Speichern des Zielfunktionswertes
            objective_value_actual = actual_model.objective_value
            df_objectives_actual = pd.DataFrame([{'Scenario': 'actual', 'ObjectiveValue': objective_value_actual}])
            objectives_file_actual = f'{PATH_OUT_ACTUAL}d_actual_{start_date_actual}_to_{end_date_actual}_{period_actual}_obj.csv'
            df_objectives_actual.to_csv(objectives_file_actual, index=False)

            print(f'\n### Actual heat demand scenario {start_date_actual} has been processed. ###')