# המרת מערכת קווים של TransCAD ל-GeoPackage, בלי TransCAD

[English](README.md)

הסקריפט `transcad_export.py` קורא את הקבצים של TransCAD ישירות ובונה GeoPackage ב-WGS84 עם שלוש שכבות:

| שכבה | תוכן |
|---|---|
| `routes` | קווי האוטובוס, עם כל השדות של טבלת הקווים |
| `stops_physical` | התחנות הפיזיות |
| `streets` | רשת הרחובות |

## לאיזה קבצים זה מתאים
רק לתיקייה של מערכת קווי אוטובוס של TransCAD במבנה הבא. השמות חייבים להיות בדיוק אלה:

- `Streets.dbd`, עם `Streets.dln`, `Streets.pts`, `Streets.BIN` ו-`Streets.DCB`
- `Bus Routes.rts` ו-`Bus Routes.rtg`
- `Bus RoutesR.bin` + `.DCB`: טבלת הקווים
- `Bus RoutesP.bin` + `.DCB`: התחנות הפיזיות, עם השדות `LongitudeN`/`LatitudeN`

הסקריפט לא מתאים לשכבות נקודות או פוליגונים אחרות, למטריצות (`.mtx`), או לרשת מחוץ לישראל.

## מה צריך להתקין
1. **Python 3**: מ-python.org, או כל Python קיים.
2. **numpy**: ספריית החוץ היחידה שהסקריפט צריך. כל השאר מגיע עם Python.
   ```
   python -m pip install numpy
   ```
3. **QGIS**: הסקריפט משתמש ב-`ogr2ogr.exe` שמגיע איתו, ומוצא אותו לבד: קודם ב-PATH, ואחר כך בהתקנת QGIS החדשה ביותר תחת `Program Files`. אם הוא לא נמצא, מעבירים את הנתיב המלא ל-`ogr2ogr.exe` כארגומנט שלישי.

## הרצה
```
python transcad_export.py "<input_folder>" "<output_folder>" ["<path\to\ogr2ogr.exe>"]
```
לדוגמה:
```
python transcad_export.py "C:\data\transcad_input" "C:\data\output"
```
ההרצה לוקחת כמה דקות. בתיקיית הפלט צריך כ-800MB פנויים.

## מה יוצא
- `RS_corrected_WGS84.gpkg`: **זה הקובץ שמשתמשים בו.** הקואורדינטות שלו מתוקנות.
- `routes.csv`, `stops_physical.csv`, `streets.csv`: קבצי ביניים עם עמודת WKT, בקואורדינטות הגולמיות של TransCAD, **לפני** תיקון הדאטום. לא לטעון אותם כ-WGS84.

## חשוב לדעת
- **תיקון דאטום:** TransCAD שומר את הקואורדינטות בדאטום ישראל 1993, לא ב-WGS84. בלי תיקון, הכול זז בכ-78 מטר. הסקריפט מתקן את זה אוטומטית, לפי אותו עיקרון כמו [israel_trancsad_fix](https://github.com/eithanwes/israel_trancsad_fix).
- **שדה `geom_status` בשכבת הקווים:**
  - `complete`: הקו שלם.
  - `filled_from_streets`: היו פערים, והם הושלמו במסלול הקצר ביותר על הרחובות, בלי להתחשב בחד-סטריות. כדאי לבדוק אותם בעין.
  - `partial`: נשארו פערים, והקו שבור.
- **התחנות לפי קו (`Bus RoutesS`) עדיין לא מומרות.**
- **הפורמט פוענח בהנדסה לאחור.** גרסה אחרת של TransCAD יכולה לשבור את הסקריפט. אחרי כל הרצה כדאי לבדוק את ההודעות שהוא מדפיס: מספר הקטעים, מספר הקווים, ופילוח הקווים לפי שלמות.

## רישיון
GPL-3.0. ראו [LICENSE](LICENSE).
