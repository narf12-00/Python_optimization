import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from itertools import product as itertools_product
import traceback
import tqdm
import pickle
import os
import psutil
import multiprocessing
import atexit
import signal
import threading
import logging

# Configurazione del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configurazione dell'accesso a Google Sheets
def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('/Users/francescomancin/Desktop/PYTHON PROJECTS/INTEGRAZIONE PY GOOGLE/integrazione-py-97177e404e4c.json', scope)
    client = gspread.authorize(creds)
    return client.open("TOOL GG-PY")

spreadsheet = setup_google_sheets()

# Directory temporanea
TEMP_DIR = './temp_combinations'

# Funzioni di utilità
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
        logging.error(f"Errore nella conversione a float: {value} - {str(e)}")
        return 'N/A'

# Funzione per ottenere i dati dai fogli
def get_data_from_sheet(sheet_name, headers_row=3, data_start_row=4):
    try:
        logging.info(f"Caricamento dati dal foglio {sheet_name}")
        sheet = spreadsheet.worksheet(sheet_name)
        all_data = sheet.get_all_values()
        headers = all_data[headers_row]
        data_rows = all_data[data_start_row:]

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
        logging.info(f"Dati filtrati per {sheet_name}: {filtered_data}")
        return filtered_data
    except Exception as e:
        logging.error(f"Errore nel caricamento dei dati dal foglio {sheet_name}: {str(e)}")
        traceback.print_exc()
        return []

def get_sheets_to_extract():
    try:
        settings_sheet = spreadsheet.worksheet("SETTINGS")
        settings_data = settings_sheet.get_all_values()
        return [row[0].strip() for row in settings_data[1:] if row[1].strip().lower() == 'true']
    except Exception as e:
        logging.error(f"Errore nel caricamento dei dati dai fogli: {str(e)}")
        return []

def get_all_data(sheets_to_extract):
    extracted_data = {}
    for sheet_name in sheets_to_extract:
        extracted_data[sheet_name] = get_data_from_sheet(sheet_name)
        time.sleep(1)  # Evita di superare la quota di richieste
    return extracted_data

def get_conditions_data():
    try:
        sheet = spreadsheet.worksheet("CONDIZIONI")
        all_data = sheet.get_all_values()
        headers = all_data[0]
        data_rows = all_data[1:]

        conditions_data = {}
        for row in data_rows:
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
        logging.error(f"Errore nel caricamento dei dati dal foglio CONDIZIONI: {str(e)}")
        traceback.print_exc()
        return {}

# Caricamento dei dati una sola volta
sheets_to_extract = get_sheets_to_extract()
extracted_data = get_all_data(sheets_to_extract)
conditions_data = get_conditions_data()

# Funzione per calcolare il costo totale
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

# Funzione per adattare la dimensione dei batch
def batch_combinations_generator(all_combinations, initial_batch_size, memory_margin_gb):
    current_batch = []
    batch_size = initial_batch_size

    for combination in itertools_product(*all_combinations):
        current_batch.append(combination)
        if len(current_batch) == batch_size:
            yield current_batch
            current_batch = []

            # Adatta la dimensione del batch in base alla memoria disponibile
            available_memory_gb = psutil.virtual_memory().available / (1024 ** 3)
            if available_memory_gb < memory_margin_gb:
                batch_size = max(1, batch_size // 2)  # Riduci il batch size
            else:
                batch_size = min(initial_batch_size, batch_size * 2)  # Aumenta il batch size

    if current_batch:
        yield current_batch

# Funzione per processare i batch
def process_batch(batch_file):
    with open(batch_file, 'rb') as f:
        batch = pickle.load(f)
        min_cost_local = float('inf')
        optimal_combination_local = None
        for combination in batch:
            combination_dict = {}
            for distributor, product_id in combination:
                if distributor not in combination_dict:
                    combination_dict[distributor] = []
                combination_dict[distributor].append(product_id)
            total_cost = calculate_total_cost(combination_dict, extracted_data, conditions_data)
            if total_cost < min_cost_local:
                min_cost_local = total_cost
                optimal_combination_local = combination_dict
    return min_cost_local, optimal_combination_local

# Funzione per trovare la combinazione ottimale
def find_optimal_combination_with_disk_persistence(extracted_data, conditions_data, memory_margin_gb=2, initial_batch_size=1000, temp_dir=TEMP_DIR):
    os.makedirs(temp_dir, exist_ok=True)
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

    min_cost = float('inf')
    optimal_combination = None

    batch_index = 0
    for batch in batch_combinations_generator(all_combinations, initial_batch_size, memory_margin_gb):
        batch_file = os.path.join(temp_dir, f'batch_{batch_index}.pkl')
        with open(batch_file, 'wb') as f:
            pickle.dump(batch, f)
        batch_index += 1

    with multiprocessing.Pool() as pool:
        results = list(tqdm.tqdm(pool.imap(process_batch, [os.path.join(temp_dir, f) for f in os.listdir(temp_dir)]), total=batch_index, desc="Processing batches"))

    for cost, combination in results:
        if cost < min_cost:
            min_cost = cost
            optimal_combination = combination

    return optimal_combination, min_cost

# Funzione di pulizia dei file temporanei
def cleanup_temp_files(temp_dir=TEMP_DIR):
    if os.path.exists(temp_dir):
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logging.info(f"File rimosso: {file_path}")
            except Exception as e:
                logging.error(f"Errore durante la rimozione del file {file_path}: {str(e)}")
        logging.info("Tutti i file temporanei sono stati rimossi.")
    else:
        logging.warning(f"La directory {temp_dir} non esiste.")

# Gestione dei segnali di interruzione
def signal_handler(sig, frame):
    logging.info("Interruzione rilevata, pulizia dei file temporanei...")
    cleanup_temp_files()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Funzione per aggiornare i risultati nel foglio di lavoro
def update_results_worksheet(optimal_combination, worksheet):
    risultati = []

    for distributore, prod_ids in optimal_combination.items():
        for prod_id in prod_ids:
            risultati.append([prod_id, distributore])

    start_row = 17
    end_row = start_row + len(risultati) - 1
    range_label = f"A{start_row}:B{end_row}"
    worksheet.update(range_name=range_label, values=risultati)

    logging.info("Risultati aggiunti al foglio di lavoro 'COMBINAZIONE'")

# Funzione per aggiungere informazioni aggiuntive al foglio di lavoro
def add_additional_info_to_worksheet(optimal_combination, extracted_data, conditions_data, worksheet):
    start_row = 17
    detailed_info = []

    for distributor, prod_ids in optimal_combination.items():
        total_weight = sum(float(prod['Peso tot']) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        total_amount_excl_iva = sum(float(prod['Importo']) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        total_amount_incl_iva = sum(float(prod['Importo']) * (1 + float(prod['Iva']) / 100) for prod in extracted_data[distributor] if prod['ID'] in prod_ids)
        
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
        worksheet.update(range_name=f"L{row_num}:Q{row_num}", values=[info])

# Esegui l'ottimizzazione e aggiorna il foglio di lavoro
if __name__ == "__main__":
    try:
        logging.info("Inizio ottimizzazione...")
        optimal_combination, min_cost = find_optimal_combination_with_disk_persistence(extracted_data, conditions_data)
        logging.info("Ottimizzazione completata.")

        logging.info(f"Combinazione ottimale: {optimal_combination}")
        logging.info(f"Costo totale minimo: {min_cost}")

        worksheet = spreadsheet.worksheet("COMBINAZIONE")

        update_results_worksheet(optimal_combination, worksheet)
        add_additional_info_to_worksheet(optimal_combination, extracted_data, conditions_data, worksheet)

        logging.info("Ulteriori informazioni aggiunte al foglio di lavoro 'COMBINAZIONE'")
    except Exception as e:
        logging.error(f"Errore durante l'esecuzione: {str(e)}")
    finally:
        cleanup_temp_files()