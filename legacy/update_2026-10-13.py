import json,re,datetime,sys
src=sys.argv[1]; out=sys.argv[2]
h=open(src,encoding='utf8').read()
pat=re.compile(r'(<script type="application/json" id="radar-data">)(.*?)(</script>)',re.S)
m=pat.search(h); d=json.loads(m.group(2))
T="2026-10-13"
def R(**k): k.setdefault('clash',''); k['firstSeen']=k['updated']=T; return k
new=[
R(id="jarrow-10k-2026",name="Jarrow 10K (Top Flight)",date="2026-10-18",venue="Monkton Stadium, Jarrow",distances=["10k"],status="act",statusText="Entries open · OpenTrack elite/Top Flight entries close Fri 16 Oct",url="https://www.runthrough.co.uk/event/jarrow-10k-junior-race-october-2026",why="Fast, flat, fully closed-road 10K starting and finishing on the track – part of the Top Flight series."),
R(id="brighton-10k-2026",name="Brighton 10K",date="2026-11-15",venue="Hove Lawns, Brighton",distances=["10k"],status="open",statusText="Entries open",url="https://runbaseevents.eventrac.co.uk/e/brighton-10k-10764",why="Flat seafront out-and-back with a quick front end – one of the South East's best 10K PB courses.",clash="7 days after Malaga HM (8 Nov)"),
R(id="fnul-nov-2026",name="Friday Night Under the Lights 5K – November",date="2026-11-27",venue="Battersea Park, London SW11",distances=["5k"],status="open",statusText="Open to sub-15:30 men / sub-18:00 women (elite races) only",url="https://data.opentrack.run/en-gb/x/2026/GBR/fnulnov26/",why="Flat two-lap evening 5K in Battersea Park with seeded waves – only the elite races still have places.",clash="2 days before target 5K (29 Nov)"),
R(id="bmaf-5k-road-2026",name="British Masters 5K Road Championships",date="2026-11-29",venue="Battersea Park, London SW11",distances=["5k"],status="closed",statusText="Entries full",url="https://bmaf.org.uk/fixtures/",why="BMAF championship 5K on the flat Battersea Park loop – masters age groups only.",clash="Same day as target 5K (29 Nov)"),
R(id="ribble-valley-10k-2026",name="Ribble Valley 10K (Top Flight Finale)",date="2026-12-27",venue="Roefield Leisure, Clitheroe",distances=["10k"],status="open",statusText="Entries open · OpenTrack closes 25 Dec",url="https://data.opentrack.run/it/o/GBR/TOPFL/",why="Top Flight series finale with a competitive front field over the festive period."),
R(id="fnul-nye-2026",name="FNUL New Year's Eve 5K",date="2026-12-31",venue="Battersea Park, London SW11",distances=["5k"],status="announced",statusText="Dated · RSVP coming soon",url="https://www.fridaynightunderthelights5k.co.uk/event-details.php",why="Seeded, flat Battersea Park 5K from the FNUL team – a chance to close the year with a PB."),
R(id="bmaf-indoor-cardiff-2027",name="BMAF Indoor 3000m & Open Events",date="2027-01-23",venue="National Indoor Athletics Centre, Cardiff",distances=["3k"],status="announced",statusText="Advance notice · entries not open",url="https://bmaf.org.uk/fixtures/",why="Masters indoor meeting with a 3000m and open track events – masters age groups only."),
R(id="bmaf-indoor-champs-2027",name="BMAF Indoor Championships",date="2027-02-20",venue="Glasgow International Arena",distances=["mile","3k"],status="announced",statusText="Advance notice · entries not open",url="https://bmaf.org.uk/fixtures/",why="British Masters indoor championships (20–21 Feb), normally including 1500m and 3000m – masters age groups only."),
R(id="fnul-feb-2027",name="FNUL 5K – February",date="2027-02-26",venue="Battersea Park, London SW11",distances=["5k"],status="announced",statusText="Dated · RSVP coming soon",url="https://www.fridaynightunderthelights5k.co.uk/event-details.php",why="Seeded evening 5K on a flat two-lap Battersea Park course with waves of up to 85."),
R(id="trafford-10k-2027",name="Trafford 10K",date="2027-03-07",venue="Partington, Manchester",distances=["10k"],status="announced",statusText="Dated · entry status unconfirmed – check organiser",url="https://haid.app/en/events/trafford-10k-2027-mqabgfvz",why="One of the UK's fastest 10K courses with deep club fields – historically sells out."),
R(id="fnul-mar-2027",name="FNUL 5K – March",date="2027-03-12",venue="Battersea Park, London SW11",distances=["5k"],status="announced",statusText="Dated · RSVP coming soon",url="https://www.fridaynightunderthelights5k.co.uk/event-details.php",why="Seeded evening 5K on a flat two-lap Battersea Park course with waves of up to 85."),
]
ids={r['id'] for r in d['races']}
d['races']=[r for r in d['races'] if r['date']>=T]+[r for r in new if r['id'] not in ids]
d['races'].sort(key=lambda r:r['date'])
d['lastChecked']=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
lines=',\n'.join('    '+json.dumps(r,ensure_ascii=False) for r in d['races'])
wl=',\n'.join('    '+json.dumps(w,ensure_ascii=False) for w in d['watching'])
js='\n{\n  "lastChecked": "%s",\n  "races": [\n%s\n  ],\n  "watching": [\n%s\n  ]\n}\n'%(d['lastChecked'],lines,wl)
json.loads(js); assert '</' not in js
h2=h[:m.start(2)]+js+h[m.end(2):]
open(out,'w',encoding='utf8').write(h2)
print(len(d['races']),d['lastChecked'])
