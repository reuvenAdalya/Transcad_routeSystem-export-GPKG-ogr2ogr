# המרת מערכת קווים של TransCAD ל-GeoPackage, בלי TransCAD

[English](README.md)

הסקריפט `transcad_export.py` קורא את הקבצים של TransCAD ישירות ובונה GeoPackage ב-WGS84 עם ארבע שכבות:

| שכבה | תוכן |
|---|---|
| `routes` | קווי האוטובוס, עם כל השדות של טבלת הקווים |
| `route_stops` | התחנות לפי קו: שיוך כל תחנה לקו ולמקטע עליו, לפי הסדר (ראו למטה) |
| `stops_physical` | התחנות הפיזיות |
| `streets` | רשת הרחובות |

## לאיזה קבצים זה מתאים
רק לתיקייה של מערכת קווי אוטובוס של TransCAD במבנה הבא. השמות חייבים להיות בדיוק אלה:

- `Streets.dbd`, עם `Streets.dln`, `Streets.pts`, `Streets.BIN` ו-`Streets.DCB`
- `Bus Routes.rts` ו-`Bus Routes.rtg`
- `Bus RoutesR.bin` + `.DCB`: טבלת הקווים
- `Bus RoutesP.bin` + `.DCB`: התחנות הפיזיות, עם השדות `LongitudeN`/`LatitudeN`
- `Bus RoutesS.r0` ו-`Bus RoutesS.bin` + `.DCB`: התחנות לפי קו

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
- `routes.csv`, `route_stops.csv`, `streets.csv`: קבצי ביניים עם עמודת WKT, בקואורדינטות הגולמיות של TransCAD, **לפני** תיקון הדאטום. לא לטעון אותם כ-WGS84.
- `stops_physical.csv`: קובץ ביניים שכבר ב-WGS84 (ראו "תיקון דאטום" למטה).

## חשוב לדעת
- **תיקון דאטום:** TransCAD שומר את הקואורדינטות בדאטום ישראל 1993, לא ב-WGS84. בלי תיקון, הכול זז בכ-78 מטר. הסקריפט מתקן את זה אוטומטית, לפי אותו עיקרון כמו [israel_trancsad_fix](https://github.com/eithanwes/israel_trancsad_fix).
  - **חריג:** בשכבה `stops_physical` המיקום נלקח מהשדות `LongitudeN`/`LatitudeN` שבטבלה, ולא מהגאומטריה של TransCAD. השדות האלה כבר ב-WGS84, ולכן השכבה הזאת לא מוזזת. בגלל זה תחנה פיזית נמצאת בדרך כלל כ-5–6 מטר מהתחנה המקבילה ב-`route_stops`: היא יושבת על המדרכה, ו-`route_stops` יושבת על ציר הרחוב.
- **שדה `geom_status` בשכבת הקווים:**
  - `complete`: הקו שלם.
  - `filled_from_streets`: היו פערים, והם הושלמו במסלול הקצר ביותר על הרחובות, בלי להתחשב בחד-סטריות. כדאי לבדוק אותם בעין.
  - `partial`: נשארו פערים, והקו שבור.
- **שכבת `route_stops`:** כל רשומה היא תחנה של קו מסוים. השדות העיקריים:
  - `ROUTE_ID`: הקו. מתחבר ל-`Route_ID` בשכבת `routes`.
  - `SEQ`: מספר התחנה בקו, לפי הסדר.
  - `MILEPOST`: המרחק מתחילת הקו, בק"מ.
  - `DIST_TO_NEXT`: המרחק לתחנה הבאה, בק"מ. ריק בתחנה האחרונה.
  - `LINK_ID`: מקטע הרחוב שהתחנה יושבת עליו. מתחבר ל-`ID` בשכבת `streets`.
  - `PHYSICAL_STOP_ID`: התחנה הפיזית. מתחבר ל-`STOP_ID` בשכבת `stops_physical`.
  - `PASS_COUNT`: כמה פעמים הקו עובר בתחנה.
  - השדות `route_*` הם פרטי הקו, ושאר השדות (שם, כתובת, `StopActivity` ועוד) מגיעים מטבלת התחנות.

  השדות `ROUTE_ID`, `MILEPOST`, `PASS_COUNT` ו-`PHYSICAL_STOP_ID` נבדקו מול ייצוא של TransCAD עצמו, והתאימו ב-100%.
- **הפורמט פוענח בהנדסה לאחור.** גרסה אחרת של TransCAD יכולה לשבור את הסקריפט. אחרי כל הרצה כדאי לבדוק את ההודעות שהוא מדפיס: מספר הקטעים, מספר הקווים, ופילוח הקווים לפי שלמות.

## רישיון
GPL-3.0. ראו [LICENSE](LICENSE).
