# Pixid Invoice Updater

Application web pour enrichir des factures SIDES (InvoicePacket) avec les données de RAV (TimeCardPacket) selon les spécifications Pixid HR-XML SIDES 2.5.

## 🚀 Démarrage rapide

### Option 1 : Utilisation locale

1. **Cloner le repository**
```bash
git clone https://github.com/votre-username/pixid-invoice-updater.git
cd pixid-invoice-updater
```

2. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

3. **Lancer l'application**
```bash
streamlit run app.py
```

L'application s'ouvrira automatiquement dans votre navigateur à l'adresse `http://localhost:8501`

### Option 2 : Déploiement sur Streamlit Cloud (Recommandé)

1. **Fork ce repository** sur votre compte GitHub

2. **Aller sur [Streamlit Cloud](https://streamlit.io/cloud)**

3. **Créer une nouvelle app** :
   - Repository : `votre-username/pixid-invoice-updater`
   - Branch : `main`
   - Main file path : `app.py`

4. **Cliquer sur Deploy!**

Votre application sera accessible à l'adresse : `https://votre-app.streamlit.app`

## 📋 Fonctionnalités

- ✅ **Préservation de l'architecture XML** : L'application ne modifie que les éléments nécessaires
- ✅ **Support multi-formats** : Compatible HR-XML SIDES 2.4 et 2.5
- ✅ **Configuration des rubriques** : Interface pour gérer les codes de paie
- ✅ **Validation en temps réel** : Vérification de la taille et du format des fichiers
- ✅ **Analyse détaillée** : Affichage des données extraites avant traitement
- ✅ **Interface intuitive** : Drag & drop pour les fichiers

## 🔧 Configuration

### Rubriques par défaut

L'application est préconfigurée avec les rubriques suivantes :

| Code   | Libellé                        | Taux   | Type |
|--------|--------------------------------|--------|------|
| 100010 | Base Contrat                   | 23.70€ | BL   |
| 100120 | Heures Supplémentaires 125%    | 29.63€ | BL   |
| 200020 | Droit Heures/Jours RTT         | 24.92€ | BL   |
| 300110 | Indemnité de Panier de Chantier| 10.30€ | SL   |
| 300120 | Indemnité de Transport         | 18.20€ | SL   |
| 400110 | Prime de Panier de Chantier    | 0.00€  | BL   |
| 400200 | Prime de 13 ème Mois           | 0.00€  | BL   |

Vous pouvez ajouter/modifier ces rubriques directement dans l'interface.

## 📁 Structure du projet

```
pixid-invoice-updater/
├── app.py                 # Application Streamlit principale
├── requirements.txt       # Dépendances Python
├── README.md             # Documentation
└── .gitignore            # Fichiers à ignorer
```

## 🛠️ Développement

### Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)

### Structure du code

Le fichier `app.py` contient :
- **Configuration** : Namespaces et rubriques par défaut
- **Fonctions utilitaires** : Parsing XML, validation, mise à jour
- **Interface Streamlit** : Composants UI et logique d'affichage

### Modifications courantes

#### Ajouter une rubrique par défaut

Dans `app.py`, modifier le dictionnaire `DEFAULT_RUBRICS` :

```python
DEFAULT_RUBRICS = {
    "100010": ("Base Contrat", 23.70, "BL"),
    "NOUVEAU_CODE": ("Nouveau Libellé", 15.00, "BL"),
    # ...
}
```

#### Modifier les limites

Pour changer la limite de taille des fichiers (20 Mo par défaut) :

```python
def validate_file_size(content: bytes, filename: str, max_size_mb: int = 30):
```

## 📄 Format des fichiers

### Fichier RAV (TimeCardPacket)

Structure attendue :
```xml
<StaffingEnvelope xmlns="http://ns.hr-xml.org/2007-04-15">
  <StaffingOrder>
    <TimeCardPacket>
      <TimeCard>
        <TimeCardId>
          <IdValue>12345</IdValue>
        </TimeCardId>
        <ReportedTime>
          <PeriodStartDate>2025-01-01</PeriodStartDate>
          <PeriodEndDate>2025-01-07</PeriodEndDate>
          <TimeInterval>
            <Id><IdValue>100010</IdValue></Id>
            <Duration>3500</Duration>
          </TimeInterval>
        </ReportedTime>
      </TimeCard>
    </TimeCardPacket>
  </StaffingOrder>
</StaffingEnvelope>
```

### Fichier Facture (InvoicePacket)

Le fichier sera enrichi avec :
- Les périodes dans `Header/UserArea/StaffingInvoiceInfo`
- Le TimeCardId dans `ReferenceInformation`
- Les lignes de facturation correspondant aux rubriques

## ⚠️ Limitations

- Taille maximale des fichiers : 20 Mo
- Formats supportés : XML uniquement
- Encodages supportés : UTF-8, ISO-8859-1

## 🐛 Dépannage

### L'application ne se lance pas

Vérifiez que toutes les dépendances sont installées :
```bash
pip install -r requirements.txt --upgrade
```

### Erreur de parsing XML

Vérifiez que vos fichiers :
- Sont bien formés (XML valide)
- Utilisent le bon namespace HR-XML
- Ne dépassent pas 20 Mo

### Les rubriques ne sont pas reconnues

Assurez-vous que les codes dans le RAV correspondent aux codes configurés dans l'application.

## 📝 Licence

Ce projet est fourni tel quel pour usage professionnel avec Pixid.

## 🤝 Support

Pour toute question relative aux spécifications Pixid, consultez la documentation officielle des interfaces XML Pixid.
