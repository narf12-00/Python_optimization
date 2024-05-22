import gspread
from oauth2client.service_account import ServiceAccountCredentials
from itertools import product as itertools_product
import traceback
import tqdm

# Configurazione dell'accesso a Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('/Users/francescomancin/Desktop/PYTHON PROJECTS/INTEGRAZIONE PY GOOGLE/integrazione-py-97177e404e4c.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open("TOOL GG-PY")

def clean_decimal(value):
    """Converte stringhe numeriche da formato locale a float, gestendo stringhe vuote e non numeriche."""
    try:
        if value.strip():  # Controlla se la stringa non è vuota dopo aver rimosso gli spazi
            clean_value = value.replace(',', '.').replace('%', '').replace('€', '').strip()
            if clean_value.startswith('<'):
                return ('<', float(clean_value[1:]))
            elif clean_value.startswith('>'):
                return ('>', float(clean_value[1:]))
            elif clean_value == 'N/A':
                return 'N/A'  # Restituisci 'N/A' per valori non numerici o N/A
            return float(clean_value)
        return 'N/A'  # Ritorna 'N/A' se la stringa è vuota o contiene solo spazi
    except ValueError as e:
        print(f"Errore nella conversione a float: {value} - {str(e)}")
        return 'N/A'  # Ritorna 'N/A' per valori non convertibili

# Dati preventivi distributori
def get_data_from_sheet(sheet_name):
    try:
        print(f"Caricamento dati dal foglio {sheet_name}")  # Debug print
        sheet = spreadsheet.worksheet(sheet_name)
        all_data = sheet.get_all_values()
        headers = all_data[3]  # Assumiamo che le intestazioni siano nella quarta riga
        data_rows = all_data[4:]  # I dati iniziano dalla quinta riga

        filtered_data = []
        # Specifichiamo i campi di interesse
        fields_of_interest = ['ID', 'Importo', 'Iva', 'Peso tot']
        for row in data_rows:
            if len(row) >= len(headers):  # Assicurati che la riga abbia abbastanza elementi
                record = {
                    headers[i]: clean_decimal(row[i]) if headers[i] in ['Importo', 'Iva', 'Peso tot'] else row[i].strip()
                    for i in range(len(headers)) if headers[i] in fields_of_interest
                }
                if record.get('ID'):  # Assicurati che ci sia un 'ID' valido
                    filtered_data.append(record)
        print(f"Dati filtrati per {sheet_name}: {filtered_data}")  # Debug print
        return filtered_data
    
    except Exception as e:
        print(f"Errore nel caricamento dei dati dal foglio {sheet_name}: {str(e)}")
        traceback.print_exc()
        return []

# Settings import (quindi i fogli da cui estrarre i dati)
def get_data_from_sheets():
    sheets_to_extract = []
    try:
        # Leggi il foglio "SETTINGS"
        settings_sheet = spreadsheet.worksheet("SETTINGS")
        settings_data = settings_sheet.get_all_values()

        for row in settings_data[1:]:  # Ignora la riga di intestazione
            sheet_name = row[0].strip()
            should_extract = row[1].strip().lower() == 'true'  # Assumiamo che le caselle selezionabili siano rappresentate come 'True' o 'False'

            if should_extract:
                # Se la casella è selezionata, aggiungi il nome del foglio a sheets_to_extract
                sheets_to_extract.append(sheet_name)

    except Exception as e:
        print(f"Errore nel caricamento dei dati dai fogli: {str(e)}")
    
    return sheets_to_extract

# Chiamata a get_data_from_sheets per aggiornare sheets_to_extract
sheets_to_extract = get_data_from_sheets()
print(f"Fogli da estrarre: {sheets_to_extract}")  # Debug print
extracted_data = {sheet: get_data_from_sheet(sheet) for sheet in sheets_to_extract}

def get_conditions_data(sheet_name, distributors):
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        all_data = sheet.get_all_values()
        headers = all_data[0]  # La seconda riga contiene le intestazioni
        data_rows = all_data[1:]  # I dati iniziano dalla terza riga

        conditions_data = {}
        for row in data_rows:
            if row[0].strip() in distributors:  # Controlla se il distributore è nell'elenco dei distributori
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

# Ottieni l'elenco dei distributori da sheets_to_extract
distributors = sheets_to_extract

# Chiamata alla funzione per ottenere i dati delle condizioni
conditions_data = get_conditions_data("CONDIZIONI", distributors)

# Stampa dei dati delle condizioni formattati
print("Dati delle Condizioni:")
for distributor, conditions in conditions_data.items():
    for condition in conditions:
        print(f"{distributor}: Peso {condition['Peso (kg)']}, Totale imponibile {condition['Totale imponibile (€)']}, Spedizione {condition['Spedizione (€ + IVA)']}, Costo Imballaggio {condition['Costo Imballaggio (€ + IVA)']}")

def calculate_total_cost(combination, extracted_data, conditions_data):
    distributor_costs = {}
    for distributor, product_ids in combination.items():
        total_amount = sum(float(next(item for item in extracted_data[distributor] if item["ID"] == product_id)['Importo']) for product_id in product_ids)
        total_amount_with_iva = sum(float(next(item for item in extracted_data[distributor] if item["ID"] == product_id)['Importo']) * (1 + float(next(item for item in extracted_data[distributor] if item["ID"] == product_id)['Iva']) / 100) for product_id in product_ids)
        total_weight = sum(float(next(item for item in extracted_data[distributor] if item["ID"] == product_id)['Peso tot']) if next(item for item in extracted_data[distributor] if item["ID"] == product_id)['Peso tot'] != 'N/A' else 0 for product_id in product_ids)

        # Calcola i costi di spedizione e imballaggio
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

    return sum(distributor_costs.values())

# Funzione per trovare la combinazione ottimale
def find_optimal_combination(extracted_data, conditions_data):
    product_ids = {product['ID'] for products in extracted_data.values() for product in products}
    distributors = list(extracted_data.keys())

    # Genera tutte le possibili combinazioni
    all_combinations = []
    for product_id in product_ids:
        product_combinations = []
        for distributor in distributors:
            for product in extracted_data[distributor]:
                if product['ID'] == product_id:
                    product_combinations.append((distributor, product_id))
        all_combinations.append(product_combinations)
        combination_count = len(product_combinations)
        print(f"Numero di combinazioni per il prodotto {product_id}: {combination_count}")

    # Trova la combinazione con il costo totale minore
    min_cost = float('inf')
    optimal_combination = None
    progress_bar = tqdm.tqdm(total=len(list(itertools_product(*all_combinations))), desc="Finding optimal combination")
    for combination in itertools_product(*all_combinations):
        combination_dict = {}
        for distributor, product_id in combination:
            if distributor not in combination_dict:
                combination_dict[distributor] = []
            combination_dict[distributor].append(product_id)
        total_cost = calculate_total_cost(combination_dict, extracted_data, conditions_data)
        if total_cost < min_cost:
            min_cost = total_cost
            optimal_combination = combination_dict
        progress_bar.update(1)
    progress_bar.close()

    return optimal_combination, min_cost

def update_results_worksheet(optimal_combination, worksheet):
    # Crea una lista vuota per i risultati
    risultati = []

    # Aggiungi i risultati alla lista
    for distributore, prod_ids in optimal_combination.items():
        for prod_id in prod_ids:
            risultati.append([prod_id, distributore])

    # Aggiungi i risultati al foglio di lavoro, a partire dalla cella A17
    start_row = 17
    end_row = start_row + len(risultati) - 1
    range_label = f"A{start_row}:B{end_row}"
    worksheet.update(range_name=range_label, values=risultati)

    print("Risultati aggiunti al foglio di lavoro 'COMBINAZIONE'")

def add_additional_info_to_worksheet(optimal_combination, extracted_data, conditions_data, worksheet):
    start_row = 17  # Riga di partenza per i risultati
    detailed_info = []

    # Preparazione delle informazioni dettagliate
    for distributor, prod_ids in optimal_combination.items():
        total_weight = sum(float(prod['Peso tot']) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        total_amount_excl_iva = sum(float(prod['Importo']) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        total_amount_incl_iva = sum(float(prod['Importo']) * (1 + float(prod['Iva']) / 100) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        
        # Calcola i costi di spedizione e imballaggio
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

        # Prepara i valori per l'aggiornamento
        info = [
            distributor,
            total_weight,
            total_amount_excl_iva,
            total_amount_incl_iva,
            shipping_cost,
            packaging_cost
        ]
        detailed_info.append(info)

    # Aggiungi le informazioni dettagliate al foglio di lavoro
    for i, info in enumerate(detailed_info):
        row_num = start_row + i
        worksheet.update(f"L{row_num}:Q{row_num}", [info])

# Esegui l'ottimizzazione e aggiorna il foglio di lavoro
if __name__ == "__main__":
    # Trova la combinazione ottimale
    print("Inizio ottimizzazione...")
    optimal_combination, min_cost = find_optimal_combination(extracted_data, conditions_data)
    print("Ottimizzazione completata.")

    # Stampa i risultati
    print(f"Combinazione ottimale: {optimal_combination}")
    print(f"Costo totale minimo: {min_cost}")

    # Ottieni il foglio di lavoro
    worksheet = spreadsheet.worksheet("COMBINAZIONE")

    # Aggiungi i risultati al foglio di lavoro
    update_results_worksheet(optimal_combination, worksheet)

    # Aggiungi le informazioni dettagliate al foglio di lavoro
    add_additional_info_to_worksheet(optimal_combination, extracted_data, conditions_data, worksheet)

    print("Ulteriori informazioni aggiunte al foglio di lavoro 'COMBINAZIONE'")