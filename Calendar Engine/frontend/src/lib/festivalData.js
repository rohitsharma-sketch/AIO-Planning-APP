import { parseDate, fmtISO } from './dateUtils'

// ─── Default Festivals ───────────────────────────────────────────────────────
// Ported verbatim from `Calendar Engine/calendar_engine.html` lines 1097-1160.
export const DEFAULT_FESTIVALS = [
  { id:1,  name:'Holi',            refDate:'2026-03-04', futDate:'2027-03-22', pre:7,  core:1, post:5  },
  { id:2,  name:'Eid al-Fitr',     refDate:'2026-03-20', futDate:'2027-03-09', pre:10, core:3, post:5  },
  { id:12, name:'Ram Navami',      refDate:'2026-03-28', futDate:'2027-04-16', pre:3,  core:1, post:2  },
  { id:13, name:'Hanuman Jayanti', refDate:'2026-04-03', futDate:'2027-04-21', pre:2,  core:1, post:1  },
  { id:14, name:'Akshaya Tritiya', refDate:'2026-04-21', futDate:'2027-05-09', pre:5,  core:1, post:2  },
  { id:15, name:'Buddha Purnima',  refDate:'2026-05-03', futDate:'2027-05-20', pre:2,  core:1, post:1  },
  { id:3,  name:'Raksha Bandhan',  refDate:'2026-08-09', futDate:'2027-08-29', pre:5,  core:1, post:3  },
  { id:4,  name:'Janmashtami',     refDate:'2026-08-14', futDate:'2027-08-04', pre:3,  core:1, post:2  },
  { id:5,  name:'Onam',            refDate:'2026-09-07', futDate:'2027-08-27', pre:10, core:2, post:4  },
  { id:6,  name:'Navratri',        refDate:'2026-10-11', futDate:'2027-09-22', pre:3,  core:9, post:2  },
  { id:7,  name:'Dussehra',        refDate:'2026-10-20', futDate:'2027-10-01', pre:3,  core:1, post:2  },
  { id:8,  name:'Dhanteras',       refDate:'2026-10-18', futDate:'2027-10-06', pre:7,  core:1, post:2  },
  { id:9,  name:'Diwali',          refDate:'2026-10-20', futDate:'2027-10-08', pre:10, core:3, post:7  },
  { id:10, name:'Bhai Dooj',       refDate:'2026-10-23', futDate:'2027-10-11', pre:1,  core:1, post:3  },
  { id:11, name:'Christmas',       refDate:'2026-12-25', futDate:'2027-12-25', pre:7,  core:2, post:5  },
];

// ─── Core (anchor-driving) festivals per cluster ──────────────────────────────
// Policy as of 2026-09-18 (explicit, supersedes the earlier "only a small
// mass-celebrated subset anchors" design from 2026-09-01): every festival on
// a cluster's list is core, full stop - no per-cluster allowlist anymore.
//
// Why: a non-core festival's Phase 1 anchor never fires, so Round A/Phase 2
// fills its TY window with whatever nearby LY date scores best independently
// per cluster - which drifts even when every cluster stores the exact same
// ref/fut date for that festival. Three separate rounds of "festival X isn't
// self-matching" bugs this session (Shraad, Raksha Bandhan, then Eid al-Fitr/
// Eid al-Adha/Christmas/Bihu/Rath Yatra) were all the same root cause: a name
// present in the profile but missing from this list. Removing the allowlist
// removes the whole bug class instead of catching one more name each time.
// generateMappings/validate (engine.js) already treat `coreNames === null` as
// "no restriction - every festival on the list is core", so this is just
// that existing behaviour made the permanent, only behaviour.
export function coreFestivalNamesFor(clusterName) {
  return null
}

// ─── Festival Date Database (2026 / 2027) ─────────────────────────────────────
// regions: ['all'] = pan-India; specific tags filter/prioritise in region-aware search
export const FESTIVAL_DB = [
  { name:'Lohri',              cat:'r', aliases:['lohdi'],                          ref:'2026-01-13', fut:'2027-01-13', pre:2, core:1, post:1,  regions:['north','punjab'] },
  { name:'Makar Sankranti',    cat:'r', aliases:['sankranti'],                      ref:'2026-01-14', fut:'2027-01-14', pre:3, core:1, post:2,  regions:['all'] },
  { name:'Uttarayan',          cat:'r', aliases:['kite festival','makar sankranti gujarat'], ref:'2026-01-14', fut:'2027-01-14', pre:3, core:1, post:2,  regions:['west','gujarat'] },
  { name:'Pongal',             cat:'r', aliases:['thai pongal'],                    ref:'2026-01-14', fut:'2027-01-14', pre:2, core:4, post:2,  regions:['south','tamil'] },
  { name:'Republic Day',       cat:'n', aliases:['republic'],                       ref:'2026-01-26', fut:'2027-01-26', pre:1, core:1, post:1,  regions:['all'] },
  { name:'Basant Panchami',    cat:'r', aliases:['saraswati puja','vasant panchami'],ref:'2026-02-02',fut:'2027-01-23', pre:2, core:1, post:1, regions:['north','east'] },
  { name:'Maha Shivaratri',    cat:'r', aliases:['shivaratri','shivratri'],         ref:'2026-02-26', fut:'2027-02-15', pre:3, core:1, post:2,  regions:['all'] },
  { name:'Holi',               cat:'r', aliases:['holika','dhulandi'],              ref:'2026-03-04', fut:'2027-03-22', pre:7, core:1, post:5,  regions:['all'] },
  { name:'Eid al-Fitr',        cat:'r', aliases:['eid','eid ul fitr','ramzan eid'], ref:'2026-03-20', fut:'2027-03-09', pre:10,core:3, post:5,  regions:['all'] },
  { name:'Gudi Padwa',         cat:'r', aliases:['ugadi','yugadi'],                 ref:'2026-03-20', fut:'2027-04-08', pre:2, core:1, post:1,  regions:['south','west','maharashtra'] },
  { name:'Ram Navami',         cat:'r', aliases:['ramnavami'],                      ref:'2026-03-28', fut:'2027-04-16', pre:3, core:1, post:2,  regions:['all'] },
  { name:'Good Friday',        cat:'r', aliases:['good friday'],                    ref:'2026-04-03', fut:'2027-03-26', pre:2, core:1, post:1,  regions:['all'] },
  { name:'Easter',             cat:'r', aliases:['easter sunday'],                  ref:'2026-04-05', fut:'2027-03-28', pre:3, core:2, post:2,  regions:['all'] },
  { name:'Hanuman Jayanti',    cat:'r', aliases:['hanuman','bajrangbali jayanti'],  ref:'2026-04-03', fut:'2027-04-21', pre:2, core:1, post:1,  regions:['all'] },
  { name:'Baisakhi',           cat:'r', aliases:['vaisakhi','vaishakhi'],           ref:'2026-04-13', fut:'2027-04-14', pre:3, core:1, post:2,  regions:['north','punjab'] },
  { name:'Bihu',               cat:'r', aliases:['rongali bihu','bohag bihu','assamese new year'], ref:'2026-04-14', fut:'2027-04-14', pre:3, core:3, post:2, regions:['east','assam'] },
  { name:'Vishu',              cat:'r', aliases:['malayali new year'],              ref:'2026-04-14', fut:'2027-04-14', pre:2, core:1, post:1,  regions:['south','kerala'] },
  { name:'Akshaya Tritiya',    cat:'r', aliases:['akha teej','akshaya triteeya'],   ref:'2026-04-21', fut:'2027-05-09', pre:5, core:1, post:2,  regions:['all'] },
  { name:'Buddha Purnima',     cat:'r', aliases:['buddha jayanti','vesak'],         ref:'2026-05-03', fut:'2027-05-20', pre:2, core:1, post:1,  regions:['all'] },
  { name:'Eid al-Adha',        cat:'r', aliases:['eid ul adha','bakrid','bakra eid'],ref:'2026-05-27',fut:'2027-05-17', pre:5, core:3, post:3, regions:['all'] },
  { name:'Rath Yatra',         cat:'r', aliases:['jagannath rath yatra','ratha yatra'], ref:'2026-07-16', fut:'2027-07-05', pre:3, core:2, post:2, regions:['east','south'] },
  { name:'Independence Day',   cat:'n', aliases:['august 15'],                      ref:'2026-08-15', fut:'2027-08-15', pre:2, core:1, post:1,  regions:['all'] },
  { name:'Raksha Bandhan',     cat:'r', aliases:['rakshabandhan','rakhi'],          ref:'2026-08-28', fut:'2027-08-17', pre:5, core:1, post:3,  regions:['all'] },
  { name:'Janmashtami',        cat:'r', aliases:['krishna janmashtami','gokulashtami'], ref:'2026-08-14', fut:'2027-08-04', pre:3, core:1, post:2, regions:['all'] },
  { name:'Ganesh Chaturthi',   cat:'r', aliases:['ganesh festival','vinayaka chaturthi'], ref:'2026-08-22', fut:'2027-09-10', pre:5, core:10,post:5, regions:['west','maharashtra','south'], regionalWindows:{'maharashtra':{pre:7,core:10,post:7}} },
  { name:'Onam',               cat:'r', aliases:['thiruvonam'],                     ref:'2026-09-07', fut:'2027-08-27', pre:10,core:2, post:4,  regions:['south','kerala'] },
  { name:'Milad-un-Nabi',      cat:'r', aliases:['milad','prophet birthday','eid milad'], ref:'2026-08-26', fut:'2027-08-15', pre:2, core:1, post:1, regions:['all'] },
  { name:'Gandhi Jayanti',     cat:'n', aliases:['gandhi'],                         ref:'2026-10-02', fut:'2027-10-02', pre:1, core:1, post:1,  regions:['all'] },
  { name:'Navratri',           cat:'r', aliases:['sharad navratri','navaratri'],    ref:'2026-10-11', fut:'2027-09-30', pre:3, core:9, post:2,  regions:['all'] },
  { name:'Navratri / Garba',   cat:'r', aliases:['garba','dandiya','navratri gujarat'], ref:'2026-10-11', fut:'2027-09-30', pre:7, core:9, post:4, regions:['west','gujarat'] },
  { name:'Durga Puja',         cat:'r', aliases:['bengali durga puja','maha saptami','maha ashtami','maha navami','vijaya dashami','puja'], ref:'2026-10-11', fut:'2027-09-30', pre:20,core:5, post:7, regions:['east','bengal'] },
  { name:'Dussehra',           cat:'r', aliases:['vijayadashami','dasara'],         ref:'2026-10-20', fut:'2027-10-09', pre:3, core:1, post:2,  regions:['all'] },
  { name:'Karva Chauth',       cat:'r', aliases:['karwa chauth','karvachauth'],     ref:'2026-10-16', fut:'2027-10-04', pre:3, core:1, post:1,  regions:['north','west'] },
  { name:'Dhanteras',          cat:'r', aliases:['dhantrayodashi','dhan teras'],    ref:'2026-10-18', fut:'2027-10-06', pre:7, core:1, post:2,  regions:['all'] },
  { name:'Diwali',             cat:'r', aliases:['deepavali','deepawali','lakshmi puja'], ref:'2026-10-20', fut:'2027-10-08', pre:10,core:3, post:7, regions:['all'] },
  { name:'Govardhan Puja',     cat:'r', aliases:['annakut','padwa'],                ref:'2026-10-21', fut:'2027-10-09', pre:1, core:1, post:2,  regions:['north','west'] },
  { name:'Bhai Dooj',          cat:'r', aliases:['bhau beej','bhai tika','bhai bij'], ref:'2026-10-23', fut:'2027-10-11', pre:1, core:1, post:3, regions:['all'] },
  { name:'Chhath Puja',        cat:'r', aliases:['chhath','chatth puja','surya shashti'], ref:'2026-10-27', fut:'2027-10-16', pre:3, core:4, post:1, regions:['north','east'] },
  { name:'Guru Nanak Jayanti', cat:'r', aliases:['gurpurab','guru nanak birthday'], ref:'2026-11-05', fut:'2027-11-24', pre:3, core:1, post:2,  regions:['north','punjab'] },
  { name:'Christmas',          cat:'r', aliases:['xmas','christmas day'],           ref:'2026-12-25', fut:'2027-12-25', pre:7, core:2, post:5,  regions:['all'] },
  // Nuakhai (Odisha's harvest festival) falls on Panchami of Bhadrapada Shukla
  // Paksha - the tithi immediately after Ganesh Chaturthi (Chaturthi) - so its
  // date is derived as Ganesh Chaturthi + 1 day rather than independently
  // sourced. Verify against a local source before relying on it for a specific
  // year; the +1 relationship can occasionally shift by a day around a
  // kshaya/adhika tithi.
  { name:'Nuakhai',            cat:'r', aliases:['nuakhai bhetghat','nua khai'],    ref:'2026-08-23', fut:'2027-09-11', pre:2, core:1, post:2,  regions:['east','odisha'] },
  // Kali Puja (Bengal) falls on the same Amavasya as Diwali/Lakshmi Puja -
  // same date every year, so it is derived directly from the Diwali entry
  // above rather than independently sourced.
  { name:'Kali Puja',          cat:'r', aliases:['shyama puja','deepannwita kali puja'], ref:'2026-10-20', fut:'2027-10-08', pre:2, core:1, post:1, regions:['east','bengal'] },
];

// ─── Multi-Year Festival Date Lookup (2025-2028) ──────────────────────────────
// Ported verbatim from `Calendar Engine/calendar_engine.html` lines 1160-1206
// (the table body is byte-identical to the source; only `export` was added).
// Dates for 2026/2027 match FESTIVAL_DB ref/fut. 2025/2028 are best estimates.
// Users can override per year-pair - stored in Local DB/festival_changelog.json.
// 2020-2024 are historical actuals; 2025-2028 as before. Years outside this
// range fall back to same month/day estimates - flagged in the sync indicator.
export const FESTIVAL_DATES = {
  'Lohri':             {'2020':'2020-01-13','2021':'2021-01-13','2022':'2022-01-13','2023':'2023-01-13','2024':'2024-01-13','2025':'2025-01-13','2026':'2026-01-13','2027':'2027-01-13','2028':'2028-01-13'},
  'Makar Sankranti':   {'2020':'2020-01-15','2021':'2021-01-14','2022':'2022-01-14','2023':'2023-01-15','2024':'2024-01-15','2025':'2025-01-14','2026':'2026-01-14','2027':'2027-01-15','2028':'2028-01-15'},
  'Uttarayan':         {'2020':'2020-01-14','2021':'2021-01-14','2022':'2022-01-14','2023':'2023-01-14','2024':'2024-01-14','2025':'2025-01-14','2026':'2026-01-14','2027':'2027-01-14','2028':'2028-01-15'},
  'Pongal':            {'2020':'2020-01-15','2021':'2021-01-14','2022':'2022-01-14','2023':'2023-01-15','2024':'2024-01-15','2025':'2025-01-14','2026':'2026-01-14','2027':'2027-01-14','2028':'2028-01-14'},
  'Republic Day':      {'2020':'2020-01-26','2021':'2021-01-26','2022':'2022-01-26','2023':'2023-01-26','2024':'2024-01-26','2025':'2025-01-26','2026':'2026-01-26','2027':'2027-01-26','2028':'2028-01-26'},
  'Basant Panchami':   {'2020':'2020-01-29','2021':'2021-02-16','2022':'2022-02-05','2023':'2023-01-26','2024':'2024-02-14','2025':'2025-02-02','2026':'2026-01-23','2027':'2027-02-11','2028':'2028-02-11'},
  'Maha Shivaratri':   {'2020':'2020-02-21','2021':'2021-03-11','2022':'2022-03-01','2023':'2023-02-18','2024':'2024-03-08','2025':'2025-02-26','2026':'2026-02-26','2027':'2027-02-15','2028':'2028-03-06'},
  'Holi':              {'2020':'2020-03-10','2021':'2021-03-29','2022':'2022-03-18','2023':'2023-03-08','2024':'2024-03-25','2025':'2025-03-14','2026':'2026-03-04','2027':'2027-03-22','2028':'2028-03-12'},
  'Eid al-Fitr':       {'2020':'2020-05-25','2021':'2021-05-14','2022':'2022-05-03','2023':'2023-04-22','2024':'2024-04-11','2025':'2025-03-30','2026':'2026-03-20','2027':'2027-03-09','2028':'2028-02-26'},
  'Gudi Padwa':        {'2020':'2020-03-25','2021':'2021-04-13','2022':'2022-04-02','2023':'2023-03-22','2024':'2024-04-09','2025':'2025-03-30','2026':'2026-03-20','2027':'2027-04-08','2028':'2028-04-06'},
  'Ram Navami':        {'2020':'2020-04-02','2021':'2021-04-21','2022':'2022-04-10','2023':'2023-03-30','2024':'2024-04-17','2025':'2025-04-06','2026':'2026-03-28','2027':'2027-04-16','2028':'2028-04-05'},
  'Good Friday':       {'2020':'2020-04-10','2021':'2021-04-02','2022':'2022-04-15','2023':'2023-04-07','2024':'2024-03-29','2025':'2025-04-18','2026':'2026-04-03','2027':'2027-03-26','2028':'2028-04-14'},
  'Easter':            {'2020':'2020-04-12','2021':'2021-04-04','2022':'2022-04-17','2023':'2023-04-09','2024':'2024-03-31','2025':'2025-04-20','2026':'2026-04-05','2027':'2027-03-28','2028':'2028-04-16'},
  'Hanuman Jayanti':   {'2020':'2020-04-08','2021':'2021-04-27','2022':'2022-04-16','2023':'2023-04-06','2024':'2024-04-23','2025':'2025-04-12','2026':'2026-04-03','2027':'2027-04-21','2028':'2028-04-13'},
  'Baisakhi':          {'2020':'2020-04-13','2021':'2021-04-13','2022':'2022-04-14','2023':'2023-04-14','2024':'2024-04-13','2025':'2025-04-13','2026':'2026-04-13','2027':'2027-04-14','2028':'2028-04-13'},
  'Bihu':              {'2020':'2020-04-14','2021':'2021-04-14','2022':'2022-04-14','2023':'2023-04-14','2024':'2024-04-14','2025':'2025-04-14','2026':'2026-04-14','2027':'2027-04-14','2028':'2028-04-14'},
  'Vishu':             {'2020':'2020-04-14','2021':'2021-04-14','2022':'2022-04-15','2023':'2023-04-15','2024':'2024-04-14','2025':'2025-04-14','2026':'2026-04-14','2027':'2027-04-14','2028':'2028-04-14'},
  'Akshaya Tritiya':   {'2020':'2020-04-26','2021':'2021-05-14','2022':'2022-05-03','2023':'2023-04-22','2024':'2024-05-10','2025':'2025-04-30','2026':'2026-04-21','2027':'2027-05-09','2028':'2028-04-28'},
  'Buddha Purnima':    {'2020':'2020-05-07','2021':'2021-05-26','2022':'2022-05-16','2023':'2023-05-05','2024':'2024-05-23','2025':'2025-05-12','2026':'2026-05-03','2027':'2027-05-20','2028':'2028-05-10'},
  'Eid al-Adha':       {'2020':'2020-08-01','2021':'2021-07-21','2022':'2022-07-10','2023':'2023-06-29','2024':'2024-06-17','2025':'2025-06-06','2026':'2026-05-27','2027':'2027-05-17','2028':'2028-05-06'},
  'Rath Yatra':        {'2020':'2020-06-23','2021':'2021-07-12','2022':'2022-07-01','2023':'2023-06-20','2024':'2024-07-07','2025':'2025-06-27','2026':'2026-07-16','2027':'2027-07-05','2028':'2028-07-04'},
  'Raksha Bandhan':    {'2020':'2020-08-03','2021':'2021-08-22','2022':'2022-08-11','2023':'2023-08-30','2024':'2024-08-19','2025':'2025-08-09','2026':'2026-08-28','2027':'2027-08-17','2028':'2028-08-18'},
  'Independence Day':  {'2020':'2020-08-15','2021':'2021-08-15','2022':'2022-08-15','2023':'2023-08-15','2024':'2024-08-15','2025':'2025-08-15','2026':'2026-08-15','2027':'2027-08-15','2028':'2028-08-15'},
  'Janmashtami':       {'2020':'2020-08-11','2021':'2021-08-30','2022':'2022-08-18','2023':'2023-09-06','2024':'2024-08-26','2025':'2025-08-16','2026':'2026-08-14','2027':'2027-08-04','2028':'2028-08-23'},
  'Ganesh Chaturthi':  {'2020':'2020-08-22','2021':'2021-09-10','2022':'2022-08-31','2023':'2023-09-19','2024':'2024-09-07','2025':'2025-08-27','2026':'2026-08-22','2027':'2027-09-10','2028':'2028-08-30'},
  'Onam':              {'2020':'2020-08-31','2021':'2021-08-21','2022':'2022-09-08','2023':'2023-08-29','2024':'2024-09-15','2025':'2025-09-05','2026':'2026-09-07','2027':'2027-08-27','2028':'2028-09-14'},
  'Milad-un-Nabi':     {'2020':'2020-10-29','2021':'2021-10-19','2022':'2022-10-09','2023':'2023-09-28','2024':'2024-09-16','2025':'2025-09-04','2026':'2026-08-26','2027':'2027-08-15','2028':'2028-08-14'},
  'Gandhi Jayanti':    {'2020':'2020-10-02','2021':'2021-10-02','2022':'2022-10-02','2023':'2023-10-02','2024':'2024-10-02','2025':'2025-10-02','2026':'2026-10-02','2027':'2027-10-02','2028':'2028-10-02'},
  'Navratri':          {'2020':'2020-10-17','2021':'2021-10-07','2022':'2022-09-26','2023':'2023-10-15','2024':'2024-10-03','2025':'2025-09-22','2026':'2026-10-11','2027':'2027-09-30','2028':'2028-10-10'},
  'Navratri / Garba':  {'2020':'2020-10-17','2021':'2021-10-07','2022':'2022-09-26','2023':'2023-10-15','2024':'2024-10-03','2025':'2025-09-22','2026':'2026-10-11','2027':'2027-09-30','2028':'2028-10-10'},
  'Durga Puja':        {'2020':'2020-10-17','2021':'2021-10-07','2022':'2022-09-26','2023':'2023-10-15','2024':'2024-10-03','2025':'2025-09-22','2026':'2026-10-11','2027':'2027-09-30','2028':'2028-10-10'},
  'Dussehra':          {'2020':'2020-10-25','2021':'2021-10-15','2022':'2022-10-04','2023':'2023-10-24','2024':'2024-10-12','2025':'2025-10-02','2026':'2026-10-20','2027':'2027-10-09','2028':'2028-10-19'},
  'Karva Chauth':      {'2020':'2020-11-04','2021':'2021-10-24','2022':'2022-10-13','2023':'2023-11-01','2024':'2024-10-20','2025':'2025-10-07','2026':'2026-10-16','2027':'2027-10-04','2028':'2028-10-24'},
  'Dhanteras':         {'2020':'2020-11-13','2021':'2021-11-02','2022':'2022-10-23','2023':'2023-11-10','2024':'2024-10-29','2025':'2025-10-18','2026':'2026-10-18','2027':'2027-10-06','2028':'2028-10-26'},
  'Diwali':            {'2020':'2020-11-14','2021':'2021-11-04','2022':'2022-10-24','2023':'2023-11-12','2024':'2024-10-31','2025':'2025-10-20','2026':'2026-11-08','2027':'2027-10-29','2028':'2028-10-28'},
  'Govardhan Puja':    {'2020':'2020-11-15','2021':'2021-11-05','2022':'2022-10-26','2023':'2023-11-14','2024':'2024-11-02','2025':'2025-10-21','2026':'2026-10-21','2027':'2027-10-09','2028':'2028-10-29'},
  'Bhai Dooj':         {'2020':'2020-11-16','2021':'2021-11-06','2022':'2022-10-27','2023':'2023-11-15','2024':'2024-11-03','2025':'2025-10-22','2026':'2026-10-23','2027':'2027-10-11','2028':'2028-10-30'},
  'Chhath Puja':       {'2020':'2020-11-20','2021':'2021-11-10','2022':'2022-10-30','2023':'2023-11-19','2024':'2024-11-07','2025':'2025-10-26','2026':'2026-11-15','2027':'2027-11-05','2028':'2028-11-02'},
  'Guru Nanak Jayanti':{'2020':'2020-11-30','2021':'2021-11-19','2022':'2022-11-08','2023':'2023-11-27','2024':'2024-11-15','2025':'2025-11-05','2026':'2026-11-05','2027':'2027-11-24','2028':'2028-11-13'},
  'Christmas':         {'2020':'2020-12-25','2021':'2021-12-25','2022':'2022-12-25','2023':'2023-12-25','2024':'2024-12-25','2025':'2025-12-25','2026':'2026-12-25','2027':'2027-12-25','2028':'2028-12-25'},
  // Derived as Ganesh Chaturthi + 1 day - see the FESTIVAL_DB comment above.
  'Nuakhai':           {'2020':'2020-08-23','2021':'2021-09-11','2022':'2022-09-01','2023':'2023-09-20','2024':'2024-09-08','2025':'2025-08-28','2026':'2026-08-23','2027':'2027-09-11','2028':'2028-08-31'},
  // Derived as identical to Diwali - see the FESTIVAL_DB comment above.
  'Kali Puja':         {'2020':'2020-11-14','2021':'2021-11-04','2022':'2022-10-24','2023':'2023-11-12','2024':'2024-10-31','2025':'2025-10-20','2026':'2026-10-20','2027':'2027-10-08','2028':'2028-10-28'},
};

// ─── Festival Name Autocomplete ───────────────────────────────────────────────
// Flat, searchable index built once from FESTIVAL_DB: every canonical name plus
// its aliases, each pointing back to that festival's canonical name. Lets the
// Festival Name input suggest-as-you-type against both the real name ("Rath
// Yatra") and common alternate spellings/nicknames ("jagannath rath yatra"),
// matching the old app's searchFestDB()-driven suggestions dropdown, which the
// React rewrite never ported (calendar_engine.html lines 1222-1301).
export const FESTIVAL_SEARCH_INDEX = FESTIVAL_DB.flatMap(f => [
  { term: f.name.toLowerCase(), canonical: f.name },
  ...(f.aliases || []).map(a => ({ term: a.toLowerCase(), canonical: f.name })),
])

// Given a query string, returns up to `limit` distinct canonical festival names
// whose name or an alias contains the query (case-insensitive substring match),
// prefix matches ranked above mid-string matches, then alphabetically.
export function suggestFestivalNames(query, limit = 8) {
  const q = query.trim().toLowerCase()
  if (q.length < 2) return []
  const seen = new Set()
  const hits = []
  for (const { term, canonical } of FESTIVAL_SEARCH_INDEX) {
    if (!term.includes(q) || seen.has(canonical)) continue
    seen.add(canonical)
    hits.push({ canonical, rank: term.startsWith(q) ? 0 : 1 })
  }
  hits.sort((a, b) => a.rank - b.rank || a.canonical.localeCompare(b.canonical))
  return hits.slice(0, limit).map(h => h.canonical)
}

// Resolves what a newly-picked festival name should fill in: refDate/futDate
// for the CURRENT ref/fut year (real FESTIVAL_DATES entry if this year has
// one, else FESTIVAL_DB's own date with the month/day kept and the year
// swapped in - same fallback rule as applyYearToProfiles below), plus
// FESTIVAL_DB's pre/core/post as a starting point the user can still adjust.
// Returns null if the name isn't in FESTIVAL_DB (a custom/local festival name
// with no known dates) - callers should leave the row's existing values alone.
export function resolveFestivalDefaults(name, refYear, futYear) {
  const dbDefault = FESTIVAL_DB.find(f => f.name === name)
  if (!dbDefault) return null
  const dbEntry = FESTIVAL_DATES[name]
  const ry = Number(refYear), fy = Number(futYear)

  function resolveOne(dbDateStr, targetYear, entryYearKey) {
    if (dbEntry && dbEntry[entryYearKey]) return dbEntry[entryYearKey]
    const d = parseDate(dbDateStr)
    return d && Number.isFinite(targetYear) ? fmtISO(new Date(targetYear, d.getMonth(), d.getDate())) : dbDateStr
  }

  return {
    refDate: resolveOne(dbDefault.ref, ry, String(ry)),
    futDate: resolveOne(dbDefault.fut, fy, String(fy)),
    pre: dbDefault.pre, core: dbDefault.core, post: dbDefault.post,
  }
}

// ─── Year Re-sync ─────────────────────────────────────────────────────────────
// Port of the old app's `autoUpdateFestivalDates(refYr, futYr)`
// (calendar_engine.html lines 2691-2721), minus its DOM re-render / saveState()
// tail - this is a pure function returning a new profiles array, so callers
// decide how to persist and re-render.
//
// Scope matches the original exactly: EVERY cluster's EVERY festival is
// rewritten, not just the one on screen.
//
// Per festival:
//   * DB entry exists and has that exact year  -> use the real date verbatim.
//   * DB entry exists but not that year        -> keep month/day, swap the year.
//   * No DB entry at all (custom festival)     -> keep month/day, swap the year.
// The month/day-preserving fallback is `new Date(yr, month, day)` verbatim from
// the original, so a Feb 29 date moving into a non-leap year rolls to Mar 1 the
// same way the old app rolled it.
//
// NOT ported (deliberate): the old app followed this with `applyYearDates()`
// (lines 2827-2860), which re-applied user per-year-pair overrides from the
// festival changelog on top of these DB dates. Nothing in the new app writes to
// /festival-changelog yet (it is read-only - see ChangeLogViewer.jsx), so there
// are no overrides to re-apply and that step is currently a no-op. When
// changelog writes are wired up, override re-application belongs right here,
// after the DB dates are applied.
//
// Returns { profiles, updated, estimated }:
//   updated   - festivals whose refDate or futDate actually changed
//   estimated - distinct festival names with no exact DB date for one or both
//               years (i.e. fell back to a month/day estimate). Mirrors the old
//               app's sync-indicator count at lines 2848-2852, which counted
//               distinct names across all clusters.
export function applyYearToProfiles(profiles, refYr, futYr) {
  const ry = Number(refYr), fy = Number(futYr)
  let updated = 0
  const estimated = new Set()

  const nextProfiles = (profiles || []).map(cp => ({
    ...cp,
    festivals: (cp.festivals || []).map(f => {
      const next = { ...f }
      const dbEntry = FESTIVAL_DATES[f.name]

      if (dbEntry) {
        const rd = dbEntry[String(ry)]
        const fd = dbEntry[String(fy)]
        if (rd) {
          next.refDate = rd
        } else {
          const d = parseDate(f.refDate)
          if (d) next.refDate = fmtISO(new Date(ry, d.getMonth(), d.getDate()))
        }
        if (fd) {
          next.futDate = fd
        } else {
          const d = parseDate(f.futDate)
          if (d) next.futDate = fmtISO(new Date(fy, d.getMonth(), d.getDate()))
        }
        if (!rd || !fd) estimated.add(f.name)
      } else {
        const rd = parseDate(f.refDate)
        const fd = parseDate(f.futDate)
        if (rd) next.refDate = fmtISO(new Date(ry, rd.getMonth(), rd.getDate()))
        if (fd) next.futDate = fmtISO(new Date(fy, fd.getMonth(), fd.getDate()))
        estimated.add(f.name)
      }

      if (next.refDate !== f.refDate || next.futDate !== f.futDate) updated++
      return next
    }),
  }))

  return { profiles: nextProfiles, updated, estimated: estimated.size }
}

// The status line the old app showed in #savedIndicator after a re-sync
// (calendar_engine.html line 2855), minus the overrides clause (no overrides
// exist yet - see applyYearToProfiles). `updated` is added here because it is
// real information the old inline table re-render conveyed visually and a
// tab-switching flow does not.
export function yearSyncMessage(refYr, futYr, updated, estimated) {
  const est = estimated
    ? ` · ${estimated} festival${estimated > 1 ? 's' : ''} estimated - verify dates`
    : ''
  return `Dates updated for ${refYr} -> ${futYr} · ${updated} festival date${updated === 1 ? '' : 's'} changed${est}`
}
