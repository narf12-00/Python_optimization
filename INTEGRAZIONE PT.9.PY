#Utilizzo di tqdm: La libreria tqdm è stata utilizzata per creare una barra di avanzamento che mostra il progresso durante l'ottimizzazione.
#Aggiornamento della barra di avanzamento: La barra di avanzamento viene aggiornata all'interno della funzione dfs ogni volta che una combinazione viene valutata.
#Questo script implementa una versione semplice della ricerca a profondità limitata (DFS con profondità limitata) per ridurre il numero di combinazioni esplorate. Il parametro max_depth può essere regolato in base alle tue esigenze e alle risorse disponibili.

# Prova a eseguire questo script e verifica se riesci a ottenere i risultati desiderati in un tempo ragionevole

#CHIEDI A COSA SERVA LA PROFONDITò

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from itertools import product as itertools_product
import traceback
import time
from tqdm import tqdm

# Configurazione dell'accesso a Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('/Users/francescomancin/Desktop/PYTHON PROJECTS/PY Google/API_key/integrazione-py-423b39a2d7af.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open("TOOL GG-PY")

def clean_decimal(value):
    try:
        if value.strip():
            clean_value = value.replace(',', '.').replace('%', '').replace('€', '').strip()
            if clean_value.startswith('<'):
                return ('<', float(clean_value[1:]))
            elif clean_value.startswith('>'):
                return ('>', float(clean_value[1:]))
            elif clean_value == 'N/A':
                return 'N/A'
            return float(clean_value)
        return 'N/A'
    except ValueError as e:
        print(f"Errore nella conversione a float: {value} - {str(e)}")
        return 'N/A'

def get_data_from_sheet(sheet_name):
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        all_data = sheet.get_all_values()
        headers = all_data[3]
        data_rows = all_data[4:]

        filtered_data = []
        fields_of_interest = ['ID', 'Importo', 'Iva', 'Peso tot']
        for row in data_rows:
            if len(row) >= len(headers):
                record = {
                    headers[i]: clean_decimal(row[i]) if headers[i] in ['Importo', 'Iva', 'Peso tot'] else row[i].strip()
                    for i in range(len(headers)) if headers[i] in fields_of_interest
                }
                if record.get('ID'):
                    filtered_data.append(record)
        return filtered_data
    
    except Exception as e:
        print(f"Errore nel caricamento dei dati dal foglio {sheet_name}: {str(e)}")
        traceback.print_exc()
        return []

def get_data_from_sheets():
    sheets_to_extract = []
    try:
        settings_sheet = spreadsheet.worksheet("SETTINGS")
        settings_data = settings_sheet.get_all_values()

        for row in settings_data[1:]:
            sheet_name = row[0].strip()
            should_extract = row[1].strip().lower() == 'true'
            if should_extract:
                sheets_to_extract.append(sheet_name)
    except Exception as e:
        print(f"Errore nel caricamento dei dati dai fogli: {str(e)}")
    
    return sheets_to_extract

sheets_to_extract = get_data_from_sheets()
extracted_data = {sheet: get_data_from_sheet(sheet) for sheet in sheets_to_extract}

def get_conditions_data(sheet_name, distributors):
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        all_data = sheet.get_all_values()
        headers = all_data[0]
        data_rows = all_data[1:]

        conditions_data = {}
        for row in data_rows:
            if row[0].strip() in distributors:
                distributor = row[0].strip()
                condition = {
                    'Peso (kg)': clean_decimal(row[1]),
                    'Totale imponibile (€)': clean_decimal(row[2]),
                    'Spedizione (€ + IVA)': clean_decimal(row[3]),
                    'Costo Imballaggio (€ + IVA)': clean_decimal(row[4])
                }
                if distributor not in conditions_data:
                    conditions_data[distributor] = []
                conditions_data[distributor].append(condition)
        return conditions_data
    except Exception as e:
        print(f"Errore nel caricamento dei dati dal foglio {sheet_name}: {str(e)}")
        traceback.print_exc()
        return {}

distributors = sheets_to_extract
conditions_data = get_conditions_data("CONDIZIONI", distributors)

product_data_index = {
    distributor: {product['ID']: product for product in products}
    for distributor, products in extracted_data.items()
}

def calculate_total_cost(combination):
    combination_dict, product_data_index, conditions_data = combination
    distributor_costs = {}
    for distributor, product_ids in combination_dict.items():
        total_amount = sum(float(product_data_index[distributor][product_id]['Importo']) for product_id in product_ids)
        total_amount_with_iva = sum(float(product_data_index[distributor][product_id]['Importo']) * (1 + float(product_data_index[distributor][product_id]['Iva']) / 100) for product_id in product_ids)
        total_weight = sum(float(product_data_index[distributor][product_id]['Peso tot']) if product_data_index[distributor][product_id]['Peso tot'] != 'N/A' else 0 for product_id in product_ids)

        shipping_cost = 0
        packaging_cost = 0
        if total_amount > 0:
            distributor_conditions = conditions_data.get(distributor, [])
            for condition in distributor_conditions:
                peso_cond = condition['Peso (kg)']
                amount_cond = condition['Totale imponibile (€)']

                weight_match = (
                    (isinstance(peso_cond, tuple) and ((peso_cond[0] == '<' and total_weight < peso_cond[1]) or (peso_cond[0] == '>' and total_weight > peso_cond[1]))) or
                    (isinstance(peso_cond, float) and total_weight == peso_cond)
                )
                amount_match = (
                    (isinstance(amount_cond, tuple) and ((amount_cond[0] == '<' and total_amount < amount_cond[1]) or (amount_cond[0] == '>' and total_amount > amount_cond[1]))) or
                    (isinstance(amount_cond, float) and total_amount == amount_cond)
                )

                if weight_match and amount_match:
                    shipping_cost = max(shipping_cost, condition['Spedizione (€ + IVA)'] if condition['Spedizione (€ + IVA)'] != 'N/A' else 0)
                    packaging_cost = max(packaging_cost, condition['Costo Imballaggio (€ + IVA)'] if condition['Costo Imballaggio (€ + IVA)'] != 'N/A' else 0)

        total_cost = total_amount_with_iva + shipping_cost + packaging_cost
        distributor_costs[distributor] = total_cost

    return sum(distributor_costs.values()), combination_dict

def find_optimal_combination(product_data_index, conditions_data, max_depth=0.5):
    product_ids = {product_id for distributor_products in product_data_index.values() for product_id in distributor_products.keys()}
    distributors = list(product_data_index.keys())

    min_cost = float('inf')
    optimal_combination = None

    def dfs(current_combination, remaining_product_ids, depth, progress_bar):
        nonlocal min_cost, optimal_combination

        if depth > max_depth:
            return

        if not remaining_product_ids:
            combination_dict = {}
            for distributor, product_id in current_combination:
                if distributor not in combination_dict:
                    combination_dict[distributor] = []
                combination_dict[distributor].append(product_id)
            total_cost, _ = calculate_total_cost((combination_dict, product_data_index, conditions_data))
            if total_cost < min_cost:
                min_cost = total_cost
                optimal_combination = combination_dict
            progress_bar.update(1)
            return

        next_product_id = remaining_product_ids[0]
        next_remaining_product_ids = remaining_product_ids[1:]

        for distributor in distributors:
            if next_product_id in product_data_index[distributor]:
                dfs(current_combination + [(distributor, next_product_id)], next_remaining_product_ids, depth + 1, progress_bar)

    total_combinations = len(distributors) ** len(product_ids)
    with tqdm(total=total_combinations, desc="Ottimizzazione in corso") as progress_bar:
        dfs([], list(product_ids), 0, progress_bar)

    return optimal_combination, min_cost

def update_results_worksheet(optimal_combination, worksheet):
    if optimal_combination is None:
        print("Nessuna combinazione ottimale trovata.")
        return
    
    risultati = [[prod_id, distributore] for distributore, prod_ids in optimal_combination.items() for prod_id in prod_ids]
    start_row = 17
    end_row = start_row + len(risultati) - 1
    range_label = f"A{start_row}:B{end_row}"
    worksheet.update(range_name=range_label, values=risultati)

def add_additional_info_to_worksheet(optimal_combination, product_data_index, conditions_data, worksheet):
    if optimal_combination is None:
        print("Nessuna combinazione ottimale trovata.")
        return
    
    start_row = 17
    detailed_info = []

    for distributor, prod_ids in optimal_combination.items():
        total_weight = sum(float(product_data_index[distributor][prod_id]['Peso tot']) for prod_id in prod_ids)
        total_amount_excl_iva = sum(float(product_data_index[distributor][prod_id]['Importo']) for prod_id in prod_ids)
        total_amount_incl_iva = sum(float(product_data_index[distributor][prod_id]['Importo']) * (1 + float(product_data_index[distributor][prod_id]['Iva']) / 100) for prod_id in prod_ids)
        
        shipping_cost = 0
        packaging_cost = 0
        for condition in conditions_data.get(distributor, []):
            peso_cond = condition['Peso (kg)']
            amount_cond = condition['Totale imponibile (€)']

            weight_match = (
                (isinstance(peso_cond, tuple) and ((peso_cond[0] == '<' and total_weight < peso_cond[1]) or (peso_cond[0] == '>' and total_weight > peso_cond[1]))) or
                (isinstance(peso_cond, float) and total_weight == peso_cond)
            )
            amount_match = (
                (isinstance(amount_cond, tuple) and ((amount_cond[0] == '<' and total_amount_excl_iva < amount_cond[1]) or (amount_cond[0] == '>' and total_amount_excl_iva > amount_cond[1]))) or
                (isinstance(amount_cond, float) and total_amount_excl_iva == amount_cond)
            )

            if weight_match and amount_match:
                shipping_cost = max(shipping_cost, condition['Spedizione (€ + IVA)'] if condition['Spedizione (€ + IVA)'] != 'N/A' else 0)
                packaging_cost = max(packaging_cost, condition['Costo Imballaggio (€ + IVA)'] if condition['Costo Imballaggio (€ + IVA)'] != 'N/A' else 0)

        info = [
            distributor,
            total_weight,
            total_amount_excl_iva,
            total_amount_incl_iva,
            shipping_cost,
            packaging_cost
        ]
        detailed_info.append(info)

    for i, info in enumerate(detailed_info):
        row_num = start_row + i
        worksheet.update(f"L{row_num}:Q{row_num}", [info])

if __name__ == "__main__":
    print("Inizio ottimizzazione...")
    start_time = time.time()
    optimal_combination, min_cost = find_optimal_combination(product_data_index, conditions_data, max_depth=10)
    end_time = time.time()
    print(f"Ottimizzazione completata in {end_time - start_time:.2f} secondi.")

    if optimal_combination is None:
        print("Nessuna combinazione ottimale trovata.")
    else:
        print(f"Combinazione ottimale: {optimal_combination}")
        print(f"Costo totale minimo: {min_cost}")

        worksheet = spreadsheet.worksheet("COMBINAZIONE")

        update_results_worksheet(optimal_combination, worksheet)

        add_additional_info_to_worksheet(optimal_combination, product_data_index, conditions_data, worksheet)

        print("Ulteriori informazioni aggiunte al foglio di lavoro 'COMBINAZIONE'")
