#!/usr/bin/env python3
"""
Pixid Invoice Updater - Application Streamlit
─────────────────────────────────────────────
Application web pour enrichir une facture SIDES (InvoicePacket) 
avec les données d'un ou plusieurs RAV.
Respecte les spécifications Pixid HR-XML SIDES 2.5.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from decimal import Decimal
from lxml import etree
import collections
from datetime import datetime
import base64
import io
from typing import Dict, Tuple, Optional, List

# Configuration de la page
st.set_page_config(
    page_title="Pixid Invoice Updater",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styles CSS personnalisés
st.markdown("""
<style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .upload-box {
        border: 2px dashed #cccccc;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        background-color: #f9f9f9;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Namespaces HR-XML SIDES
NS_2007 = {"ns": "http://ns.hr-xml.org/2007-04-15", "oa": "http://www.openapplications.org/oagis"}
NS_2004 = {"ns": "http://ns.hr-xml.org/2004-08-02", "oa": "http://www.openapplications.org/oagis"}

# Configuration des rubriques par défaut
DEFAULT_RUBRICS = {
    "100010": ("Base Contrat", 23.70, "BL"),
    "100120": ("Heures Supplémentaires 125%", 29.63, "BL"),
    "200020": ("Droit Heures/Jours RTT", 24.92, "BL"),
    "300110": ("Indemnité de Panier de Chantier", 10.30, "SL"),
    "300120": ("Indemnité de Transport", 18.20, "SL"),
    "400110": ("Prime de Panier de Chantier", 0.00, "BL"),
    "400200": ("Prime de 13 ème Mois", 0.00, "BL"),
}

# ═══════════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_rubrics():
    """Charge les rubriques depuis la session ou les valeurs par défaut"""
    if 'rubrics' not in st.session_state:
        st.session_state.rubrics = DEFAULT_RUBRICS.copy()
    return st.session_state.rubrics

def detect_namespace(tree):
    """Détecte le namespace utilisé dans le document"""
    root = tree.getroot()
    ns_map = root.nsmap
    default_ns = ns_map.get(None, "")
    
    if "2007-04-15" in default_ns:
        return NS_2007
    elif "2004-08-02" in default_ns:
        return NS_2004
    else:
        if root.tag.endswith("StaffingEnvelope"):
            return NS_2007
        else:
            return NS_2004

def validate_file_size(content: bytes, filename: str, max_size_mb: int = 20) -> Tuple[bool, str]:
    """Valide que le fichier ne dépasse pas la limite Pixid"""
    size_bytes = len(content)
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb > max_size_mb:
        return False, f"Fichier trop volumineux: {size_mb:.2f} Mo (limite: {max_size_mb} Mo)"
    
    return True, f"Taille: {size_mb:.2f} Mo"

def read_rav_content(rav_content: str) -> Tuple[Dict[str, Decimal], str, str, str, List[Dict]]:
    """Parse le contenu XML du RAV et extrait les informations"""
    parser = etree.XMLParser(remove_blank_text=True, ns_clean=True, recover=True)
    tree = etree.fromstring(rav_content.encode('utf-8'), parser)
    
    ns = detect_namespace(etree.ElementTree(tree))
    
    qty_dict = collections.defaultdict(Decimal)
    all_periods = []
    timecard_id = ""
    details = []
    
    # Chercher les TimeCard
    for timecard in tree.xpath(".//ns:TimeCard", namespaces=ns):
        # Récupérer l'ID
        tc_id = None
        tc_id_elem = timecard.find(".//ns:TimeCardId/ns:IdValue", namespaces=ns)
        if tc_id_elem is not None:
            tc_id = tc_id_elem.text
        
        if not tc_id:
            tc_id_elem = timecard.find("ns:Id/ns:IdValue", namespaces=ns)
            if tc_id_elem is not None:
                tc_id = tc_id_elem.text
        
        if tc_id and not timecard_id:
            timecard_id = tc_id
        
        # Récupérer les périodes
        reported_time = timecard.find(".//ns:ReportedTime", namespaces=ns)
        if reported_time is not None:
            period_start = reported_time.findtext("ns:PeriodStartDate", namespaces=ns)
            period_end = reported_time.findtext("ns:PeriodEndDate", namespaces=ns)
            if period_start and period_end:
                all_periods.append((period_start, period_end))
        
        if not all_periods:
            period_start = timecard.findtext("ns:PeriodStartDate", namespaces=ns)
            period_end = timecard.findtext("ns:PeriodEndDate", namespaces=ns)
            if period_start and period_end:
                all_periods.append((period_start, period_end))
        
        # Récupérer les TimeInterval
        for time_interval in timecard.xpath(".//ns:TimeInterval", namespaces=ns):
            code = None
            
            code_elem = time_interval.find("ns:Id/ns:IdValue", namespaces=ns)
            if code_elem is not None:
                code = code_elem.text
            
            if not code:
                code_elem = time_interval.find("ns:RateOrAmount/ns:Id/ns:IdValue", namespaces=ns)
                if code_elem is not None:
                    code = code_elem.text
            
            if not code:
                code_elem = time_interval.find("ns:PayTypeCode", namespaces=ns)
                if code_elem is not None:
                    code = code_elem.text
            
            duration_str = time_interval.findtext("ns:Duration", default="0", namespaces=ns)
            
            if code and duration_str and duration_str != "0":
                duration_centimes = Decimal(duration_str.replace(",", "."))
                heures = duration_centimes / Decimal("100")
                qty_dict[code] += heures
                
                details.append({
                    'code': code,
                    'heures': float(heures),
                    'timecard_id': tc_id
                })
    
    if all_periods:
        period_start = min(period[0] for period in all_periods)
        period_end = max(period[1] for period in all_periods)
    else:
        period_start = ""
        period_end = ""
    
    return dict(qty_dict), period_start, period_end, timecard_id, details

def update_invoice(invoice_content: str, rav_data: Dict) -> str:
    """Met à jour la facture avec les données du RAV"""
    qty_dict = rav_data['quantities']
    period_start = rav_data['period_start']
    period_end = rav_data['period_end']
    timecard_id = rav_data['timecard_id']
    rubrics = load_rubrics()
    
    # Parser la facture
    parser = etree.XMLParser(remove_blank_text=True, encoding='ISO-8859-1')
    try:
        tree = etree.fromstring(invoice_content.encode('ISO-8859-1'), parser)
    except:
        parser = etree.XMLParser(remove_blank_text=True, encoding='UTF-8')
        tree = etree.fromstring(invoice_content.encode('UTF-8'), parser)
    
    ns = detect_namespace(etree.ElementTree(tree))
    
    # Trouver l'Invoice
    invoice = tree.find(".//ns:Invoice", namespaces=ns)
    if invoice is None:
        invoice = tree.find(".//Invoice")
    
    if invoice is None:
        raise ValueError("Structure Invoice non trouvée")
    
    # 1. Mise à jour des périodes
    header = invoice.find(".//{%s}Header" % ns["oa"])
    if header is not None:
        user_area = header.find("{%s}UserArea" % ns["oa"])
        if user_area is None:
            user_area = etree.SubElement(header, "{%s}UserArea" % ns["oa"])
        
        staffing_info = user_area.find("ns:StaffingInvoiceInfo", namespaces=ns)
        if staffing_info is None:
            staffing_info = user_area.find("StaffingInvoiceInfo")
        if staffing_info is None:
            staffing_info = etree.SubElement(user_area, "{%s}StaffingInvoiceInfo" % ns["ns"])
        
        # Mettre à jour les DataInformation
        period_start_exists = False
        period_end_exists = False
        
        for data_info in staffing_info.findall(".//DataInformation"):
            name = data_info.get("name")
            if name == "PeriodStart":
                data_info.set("value", period_start)
                period_start_exists = True
            elif name == "PeriodEnd":
                data_info.set("value", period_end)
                period_end_exists = True
        
        if not period_start_exists and period_start:
            data_info = etree.SubElement(staffing_info, "DataInformation")
            data_info.set("name", "PeriodStart")
            data_info.set("value", period_start)
        
        if not period_end_exists and period_end:
            data_info = etree.SubElement(staffing_info, "DataInformation")
            data_info.set("name", "PeriodEnd")
            data_info.set("value", period_end)
    
    # 2. Mise à jour du TimeCardId
    ref_info = invoice.find(".//ns:ReportedTime/ns:ReferenceInformation", namespaces=ns)
    if ref_info is None:
        ref_info = invoice.find(".//ns:ReferenceInformation", namespaces=ns)
    
    if ref_info is not None and timecard_id:
        timecard_elem = ref_info.find("ns:TimeCardId", namespaces=ns)
        if timecard_elem is None:
            insert_position = None
            for i, elem in enumerate(ref_info):
                if elem.tag.endswith("StaffingSupplierOrgUnitId"):
                    insert_position = i + 1
            
            timecard_elem = etree.Element("{%s}TimeCardId" % ns["ns"])
            timecard_elem.set("idOwner", "EXT0")
            id_value = etree.SubElement(timecard_elem, "{%s}IdValue" % ns["ns"])
            id_value.text = timecard_id
            
            if insert_position is not None:
                ref_info.insert(insert_position, timecard_elem)
            else:
                ref_info.append(timecard_elem)
    
    # 3. Mise à jour des lignes de facturation
    main_line = invoice.find(".//{%s}Line[{%s}LineNumber='1']" % (ns["oa"], ns["oa"]))
    
    if main_line is not None:
        # Mettre à jour la description
        desc_elems = main_line.findall("{%s}Description" % ns["oa"])
        for desc in desc_elems:
            if desc.text and "Prestations du" in desc.text and period_start and period_end:
                desc.text = f"Prestations du {period_start} au {period_end}"
        
        # Gérer les sous-lignes
        existing_lines = {}
        existing_line_numbers = []
        
        for subline in main_line.findall("{%s}Line" % ns["oa"]):
            desc_elem = subline.find("{%s}Description" % ns["oa"])
            line_num_elem = subline.find("{%s}LineNumber" % ns["oa"])
            
            if line_num_elem is not None:
                existing_line_numbers.append(line_num_elem.text)
            
            if desc_elem is not None and desc_elem.text:
                existing_lines[desc_elem.text] = subline
        
        # Déterminer le prochain numéro
        if existing_line_numbers:
            max_num = 0
            for num in existing_line_numbers:
                try:
                    parts = num.split('.')
                    if len(parts) > 1:
                        sub_num = int(parts[-1])
                        if sub_num > max_num:
                            max_num = sub_num
                except:
                    pass
            next_line_number = max_num + 1
        else:
            next_line_number = 1
        
        # Traiter les rubriques
        total_heures = Decimal("0.00")
        total_montant_ht = Decimal("0.00")
        
        # Calculer les totaux existants
        for subline in existing_lines.values():
            qty_elem = subline.find("{%s}ItemQuantity" % ns["oa"])
            charge_elem = subline.find(".//{%s}Total" % ns["oa"])
            
            if qty_elem is not None and qty_elem.text:
                qty = Decimal(qty_elem.text.replace(",", "."))
                total_heures += qty
            
            if charge_elem is not None and charge_elem.text:
                montant = Decimal(charge_elem.text.replace(",", "."))
                total_montant_ht += montant
        
        # Ajouter/mettre à jour les nouvelles rubriques
        for code, heures in sorted(qty_dict.items()):
            if not code or heures == 0:
                continue
            
            heures = heures.quantize(Decimal("0.00"))
            
            if code in rubrics:
                libelle, taux, type_ligne = rubrics[code]
                taux = Decimal(str(taux))
            else:
                libelle = f"Rubrique {code}"
                taux = Decimal("0.00")
                type_ligne = "BL"
            
            montant = (heures * taux).quantize(Decimal("0.01"))
            
            if libelle not in existing_lines:
                # Créer une nouvelle ligne
                new_line = etree.SubElement(main_line, "{%s}Line" % ns["oa"])
                
                line_num = etree.SubElement(new_line, "{%s}LineNumber" % ns["oa"])
                line_num.text = f"1.{next_line_number}"
                next_line_number += 1
                
                desc = etree.SubElement(new_line, "{%s}Description" % ns["oa"])
                desc.text = libelle
                
                reason = etree.SubElement(new_line, "{%s}ReasonCode" % ns["oa"])
                reason.text = type_ligne
                
                charges = etree.SubElement(new_line, "{%s}Charges" % ns["oa"])
                charge = etree.SubElement(charges, "{%s}Charge" % ns["oa"])
                total = etree.SubElement(charge, "{%s}Total" % ns["oa"])
                total.set("currency", "EUR")
                total.text = str(montant).replace(".", ",")
                
                if taux > 0:
                    price = etree.SubElement(new_line, "{%s}Price" % ns["oa"])
                    amount = etree.SubElement(price, "{%s}Amount" % ns["oa"])
                    amount.set("currency", "EUR")
                    amount.text = str(taux).replace(".", ",")
                    
                    func_amount = etree.SubElement(price, "{%s}FunctionalAmount" % ns["oa"])
                    func_amount.set("currency", "EUR")
                    func_amount.text = "12.46000"
                    
                    per_qty = etree.SubElement(price, "{%s}PerQuantity" % ns["oa"])
                    per_qty.set("uom", "percent")
                    per_qty.text = "1.90"
                
                item_qty = etree.SubElement(new_line, "{%s}ItemQuantity" % ns["oa"])
                item_qty.set("uom", "hur" if "Heure" in libelle else "pce")
                item_qty.text = str(heures).replace(".", ",")
                
                total_heures += heures
                total_montant_ht += montant
        
        # Mettre à jour les totaux
        main_charges = main_line.find(".//{%s}Total" % ns["oa"])
        if main_charges is not None:
            main_charges.text = str(total_montant_ht).replace(".", ",")
        
        main_qty = main_line.find("{%s}ItemQuantity" % ns["oa"])
        if main_qty is not None:
            main_qty.text = str(total_heures).replace(".", ",")
        
        # Totaux dans le Header
        if header is not None:
            total_charges = header.find("{%s}TotalCharges" % ns["oa"])
            if total_charges is not None:
                total_charges.text = str(total_montant_ht).replace(".", ",")
            
            total_tax = header.find("{%s}TotalTax" % ns["oa"])
            if total_tax is not None:
                tva = (total_montant_ht * Decimal("0.20")).quantize(Decimal("0.01"))
                total_tax.text = str(tva).replace(".", ",")
            
            total_amount = header.find("{%s}TotalAmount" % ns["oa"])
            if total_amount is not None:
                ttc = total_montant_ht + (total_montant_ht * Decimal("0.20"))
                ttc = ttc.quantize(Decimal("0.01"))
                total_amount.text = str(ttc).replace(".", ",")
    
    # Retourner le XML
    encoding = 'ISO-8859-1'
    if 'encoding="UTF-8"' in invoice_content or "encoding='UTF-8'" in invoice_content:
        encoding = 'UTF-8'
    
    return etree.tostring(tree, encoding=encoding, pretty_print=True, xml_declaration=True).decode(encoding)

# ═══════════════════════════════════════════════════════════════════════════
# INTERFACE STREAMLIT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # En-tête
    st.title("📄 Pixid Invoice Updater")
    st.markdown("**Enrichissement de factures SIDES avec données RAV**")
    st.markdown("Compatible HR-XML SIDES 2.4 / 2.5 et formats Pixid")
    
    # Sidebar pour la configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Gestion des rubriques
        st.subheader("📋 Rubriques")
        
        rubrics = load_rubrics()
        
        # Afficher les rubriques actuelles
        with st.expander("Voir les rubriques configurées", expanded=False):
            for code, (libelle, taux, type_ligne) in rubrics.items():
                st.text(f"{code}: {libelle} ({taux}€/{type_ligne})")
        
        # Ajouter une nouvelle rubrique
        st.markdown("### Ajouter une rubrique")
        new_code = st.text_input("Code rubrique", key="new_code")
        new_libelle = st.text_input("Libellé", key="new_libelle")
        new_taux = st.number_input("Taux horaire (€)", min_value=0.0, step=0.01, key="new_taux")
        new_type = st.selectbox("Type", ["BL", "SL"], key="new_type")
        
        if st.button("➕ Ajouter"):
            if new_code and new_libelle:
                rubrics[new_code] = (new_libelle, float(new_taux), new_type)
                st.session_state.rubrics = rubrics
                st.success(f"Rubrique {new_code} ajoutée!")
                st.rerun()
        
        # Réinitialiser les rubriques
        if st.button("🔄 Réinitialiser les rubriques"):
            st.session_state.rubrics = DEFAULT_RUBRICS.copy()
            st.success("Rubriques réinitialisées!")
            st.rerun()
    
    # Contenu principal
    tabs = st.tabs(["📥 Traitement", "📖 Documentation", "ℹ️ À propos"])
    
    with tabs[0]:
        # Zone de traitement
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📄 Fichier RAV (TimeCardPacket)")
            rav_file = st.file_uploader(
                "Glissez votre fichier RAV ici",
                type=['xml'],
                key="rav_upload",
                help="Fichier contenant les données de temps (TimeCard)"
            )
            
            if rav_file:
                # Validation de la taille
                valid, msg = validate_file_size(rav_file.getvalue(), rav_file.name)
                if valid:
                    st.success(f"✓ {rav_file.name} - {msg}")
                else:
                    st.error(f"✗ {msg}")
        
        with col2:
            st.markdown("### 📄 Fichier Facture (InvoicePacket)")
            invoice_file = st.file_uploader(
                "Glissez votre fichier facture ici",
                type=['xml'],
                key="invoice_upload",
                help="Fichier de facture à enrichir"
            )
            
            if invoice_file:
                # Validation de la taille
                valid, msg = validate_file_size(invoice_file.getvalue(), invoice_file.name)
                if valid:
                    st.success(f"✓ {invoice_file.name} - {msg}")
                else:
                    st.error(f"✗ {msg}")
        
        # Bouton de traitement
        if rav_file and invoice_file:
            st.markdown("---")
            
            if st.button("🚀 Lancer le traitement", type="primary", use_container_width=True):
                try:
                    with st.spinner("Analyse des fichiers en cours..."):
                        # Décoder les fichiers
                        rav_content = rav_file.getvalue().decode('utf-8', errors='replace')
                        invoice_content = invoice_file.getvalue().decode('utf-8', errors='replace')
                        
                        # Analyser le RAV
                        qty_dict, period_start, period_end, timecard_id, details = read_rav_content(rav_content)
                        
                        # Afficher l'analyse
                        st.markdown("### 📊 Analyse des fichiers")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("#### RAV")
                            st.info(f"""
                            - **Période**: {period_start} → {period_end}
                            - **TimeCard ID**: {timecard_id}
                            - **Rubriques trouvées**: {len(qty_dict)}
                            """)
                            
                            # Détails des rubriques
                            if qty_dict:
                                rubrics = load_rubrics()
                                total_heures = Decimal("0")
                                total_montant = Decimal("0")
                                
                                data = []
                                for code, heures in qty_dict.items():
                                    heures = heures.quantize(Decimal("0.00"))
                                    if code in rubrics:
                                        libelle, taux, type_ligne = rubrics[code]
                                        taux = Decimal(str(taux))
                                    else:
                                        libelle = f"Rubrique {code}"
                                        taux = Decimal("0")
                                        type_ligne = "BL"
                                    
                                    montant = (heures * taux).quantize(Decimal("0.01"))
                                    total_heures += heures
                                    total_montant += montant
                                    
                                    data.append({
                                        'Code': code,
                                        'Libellé': libelle,
                                        'Heures': float(heures),
                                        'Taux': float(taux),
                                        'Montant': float(montant),
                                        'Type': type_ligne
                                    })
                                
                                df = pd.DataFrame(data)
                                st.dataframe(df, use_container_width=True)
                                st.success(f"**Total**: {float(total_heures)} heures - {float(total_montant)}€ HT")
                        
                        with col2:
                            st.markdown("#### Facture")
                            # Analyser la facture
                            parser = etree.XMLParser(remove_blank_text=True)
                            tree = etree.fromstring(invoice_content.encode('utf-8'), parser)
                            root_tag = tree.tag.split('}')[-1] if '}' in tree.tag else tree.tag
                            
                            ns = detect_namespace(etree.ElementTree(tree))
                            invoice = tree.find(".//ns:Invoice", namespaces=ns)
                            if invoice is None:
                                invoice = tree.find(".//Invoice")
                            
                            info_text = f"- **Structure**: {root_tag}\n"
                            info_text += f"- **Namespace**: {'2007-04-15' if ns == NS_2007 else '2004-08-02'}\n"
                            
                            if invoice is not None:
                                # Compter les lignes existantes
                                main_line = invoice.find(".//{%s}Line[{%s}LineNumber='1']" % (ns["oa"], ns["oa"]))
                                if main_line is not None:
                                    sublines = main_line.findall("{%s}Line" % ns["oa"])
                                    info_text += f"- **Lignes existantes**: {len(sublines)}\n"
                            
                            st.info(info_text)
                    
                    # Traitement
                    with st.spinner("Mise à jour de la facture..."):
                        rav_data = {
                            'quantities': qty_dict,
                            'period_start': period_start,
                            'period_end': period_end,
                            'timecard_id': timecard_id
                        }
                        
                        updated_content = update_invoice(invoice_content, rav_data)
                        
                        # Succès
                        st.markdown("---")
                        st.success("✅ **Facture mise à jour avec succès!**")
                        
                        # Aperçu
                        with st.expander("📋 Aperçu du fichier généré", expanded=False):
                            lines = updated_content.split('\n')[:50]
                            preview = '\n'.join(lines)
                            if len(updated_content.split('\n')) > 50:
                                preview += "\n... (fichier tronqué pour l'affichage)"
                            st.code(preview, language='xml')
                        
                        # Téléchargement
                        output_filename = invoice_file.name.replace('.xml', '_enriched.xml')
                        
                        encoding = 'ISO-8859-1'
                        if 'encoding="UTF-8"' in updated_content:
                            encoding = 'UTF-8'
                        
                        st.download_button(
                            label="💾 Télécharger le fichier enrichi",
                            data=updated_content.encode(encoding),
                            file_name=output_filename,
                            mime="text/xml",
                            type="primary",
                            use_container_width=True
                        )
                        
                        # Résumé
                        st.info("""
                        ✅ **Modifications effectuées:**
                        - Périodes ajoutées/mises à jour dans UserArea
                        - TimeCardId ajouté dans ReferenceInformation
                        - Lignes de facturation enrichies avec les données du RAV
                        - Totaux recalculés (HT, TVA, TTC)
                        - Architecture XML originale préservée
                        """)
                
                except Exception as e:
                    st.error(f"❌ Erreur lors du traitement: {str(e)}")
                    with st.expander("Détails de l'erreur"):
                        st.code(str(e))
    
    with tabs[1]:
        # Documentation
        st.markdown("""
        ## 📖 Guide d'utilisation
        
        ### 1. Préparer vos fichiers
        
        - **Fichier RAV** : Doit contenir les données de temps (TimeCardPacket)
        - **Fichier Facture** : Doit être une facture SIDES (InvoicePacket)
        - Les deux fichiers doivent être au format HR-XML SIDES
        
        ### 2. Configuration des rubriques
        
        Utilisez la barre latérale pour :
        - Voir les rubriques configurées
        - Ajouter de nouvelles rubriques
        - Réinitialiser la configuration
        
        ### 3. Traitement
        
        1. Chargez vos deux fichiers XML
        2. Vérifiez l'analyse affichée
        3. Cliquez sur "Lancer le traitement"
        4. Téléchargez le fichier enrichi
        
        ### 4. Résultat
        
        Le fichier généré contient :
        - Les périodes du RAV
        - L'identifiant TimeCard
        - Les lignes de facturation mises à jour
        - Les totaux recalculés
        
        ### ⚠️ Important
        
        - Limite de taille : 20 Mo par fichier
        - Formats supportés : HR-XML SIDES 2.4 et 2.5
        - L'architecture XML originale est préservée
        """)
    
    with tabs[2]:
        # À propos
        st.markdown("""
        ## ℹ️ À propos
        
        ### Pixid Invoice Updater
        
        **Version**: 1.0.0  
        **Compatible**: HR-XML SIDES 2.4 / 2.5 et formats Pixid
        
        ### Fonctionnalités
        
        - ✅ Préservation de l'architecture XML originale
        - ✅ Support des namespaces 2004-08-02 et 2007-04-15
        - ✅ Détection automatique du format
        - ✅ Validation de la taille des fichiers
        - ✅ Configuration des rubriques personnalisable
        - ✅ Interface intuitive avec Streamlit
        
        ### Support
        
        Pour toute question ou problème :
        - Vérifiez que vos fichiers sont au format HR-XML SIDES
        - Assurez-vous que les rubriques sont correctement configurées
        - Consultez la documentation Pixid pour les spécifications
        
        ### Développement
        
        Application développée avec :
        - Python 3.8+
        - Streamlit
        - lxml pour le traitement XML
        - Architecture modulaire et maintenable
        """)

# ═══════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
