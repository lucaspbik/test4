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

## Weiterentwicklungsideen

- Persistente Speicherung (z. B. über eine relationale Datenbank).
- Feinplanung mit Schichtkalendern und Prioritäten.
- Integration von Einkauf und Lieferantenbewertung.
- Weboberfläche oder REST-API für eine benutzerfreundliche Bedienung.
