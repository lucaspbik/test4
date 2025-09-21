# ERP-System für einen Sondermaschinenbauer

Dieses Repository enthält ein leichtgewichtiges ERP-Grundsystem, das auf die
Prozesse eines Sondermaschinenbauers mit den Fertigungsverfahren Drehen,
Fräsen, Laserschneiden, Kanten, Schweißen, Schleifen und Sägen zugeschnitten
ist. Die Implementierung ist vollständig in Python gehalten und stellt
Domänenmodelle, ein In-Memory-Datenmanagement sowie zentrale Services für
Terminplanung, Materialwirtschaft und Rückmeldungen bereit.

## Funktionsumfang

- **Stammdatenverwaltung** für Kunden, Maschinenressourcen und Material.
- **Fertigungsaufträge** mit mehrstufigen Operationen inkl. Rüst- und
  Bearbeitungszeiten.
- **Kapazitätsplanung** mit automatischer Zuordnung der Operationen zu den
  passenden Maschinen und Ermittlung von Überlasten.
- **Materialdisposition** mit Ermittlung von Bedarfen und Bestandslücken.
- **Zeitdatenerfassung** zur Gegenüberstellung von Soll- und Ist-Zeiten.
- **Persistente Speicherung** aller Stammdaten, Aufträge und Rückmeldungen in
  einer SQLite-Datenbank.
- **Feinplanung** über frei definierbare Schichtkalender mit Feiertags- und
  Ausnahmeregeln sowie Priorisierung des Auftrags-Backlogs.
- **Einkaufsintegration** mit Lieferantenbewertungen, automatischer
  Bestellvorschlagserstellung und Lieferantenempfehlungen.
- **Feinabstimmung der Planung** über konfigurierbare Parameter für
  Prioritäten, Horizonte, Pufferzeiten und Beschaffungsstrategien.
- **Simulation alternativer Planungsszenarien** zur Bewertung unterschiedlicher
  Regelwerke und Startpunkte.
- **Automatische Fertigungsunterlagen** mit prozessspezifischen Checklisten und
  Arbeitsanweisungen für jede Operation.
- **Rollenbasierte Benutzerverwaltung** für Administratoren, Planung, Einkauf
  und Fertigung in der Weboberfläche.
- **Weboberfläche** auf Basis von FastAPI und Jinja2 zur Bedienung der
  wichtigsten ERP-Funktionen.

## Projektstruktur

```
erp_system/
├── __init__.py          # Paketexporte
├── domain.py            # Domänenmodelle und Enums
├── repository.py        # Generische In-Memory-Repositories
├── services.py          # Service-Fassade inkl. Planung und Materialwirtschaft
└── sample_usage.py      # Beispielskript für einen kompletten Ablauf
```

## Verwendung

1. Python 3.11 oder höher installieren.
2. Innerhalb des Repository-Verzeichnisses das Beispielskript ausführen:

   ```bash
   python -m erp_system.sample_usage
   ```

   Das Skript erzeugt Stammdaten, legt einen Produktionsauftrag an, plant die
   Operationen und gibt Kapazitäts- sowie Materialberichte aus.

3. Die Services lassen sich einfach in eigene Anwendungen integrieren, indem
   eine Instanz von `ERPService` verwendet wird. Über die Methode
   `build_operation` können individuelle Fertigungsschritte mit den geforderten
   Fertigungsverfahren modelliert werden.

## Weboberfläche starten

1. Abhängigkeiten installieren:

   ```bash
   pip install -r requirements.txt
   ```

2. Web-App mit uvicorn starten:

   ```bash
   uvicorn erp_system.web:create_app --reload
   ```

   Beim ersten Start werden automatisch Beispielstammdaten, Aufträge,
   Lieferanten und Schichtkalender angelegt. Die Oberfläche bietet Zugriff auf
   Dashboard, Feinplanung, Simulation, Einkauf, Lieferantenverwaltung,
   Benutzeradministration und Schichtplanung. In der Feinplanung lassen sich
   Prioritätsgewichte, Planungshorizont, Rüstzeitpuffer und automatische
   Freigaben konfigurieren. Der Bereich Simulation erlaubt den Vergleich
   alternativer Szenarien hinsichtlich Auslastung und Fertigstellung.
   Zusätzlich stellt die Seite *Fertigungsunterlagen* automatisch generierte
   Arbeitsanweisungen bereit, während die Benutzerverwaltung Rollen und
   Aktivierungsstatus steuert. Der Bereich Einkauf ermöglicht die Anpassung des
   Bestellmultiplikators, der Sicherheitsbestände sowie das direkte Auslösen von
   Bestellungen aus Materialbedarfen.

## Weiterentwicklungsideen

- KI-gestützte Kapazitätsglättung mit automatischem Vorschlag alternativer
  Schichtmodelle.
- Integration von Qualitätsdaten und Prüfprotokollen in die
  Fertigungsunterlagen.
- Mobile Rückmeldungen und Andon-Anbindung für die Fertigungslinien.
