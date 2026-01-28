# Example Queries

Real examples of what you can ask Helio.

## Annual Energy

Calculate yearly energy production:

```
What's the annual energy for a 10kW system in Sydney?
→ A 10 kW system in Sydney produces approximately 17,453 kWh annually

How much energy does a 5kW system produce in Berlin?
→ A 5 kW system in Berlin produces approximately 4,850 kWh annually
```

## Tilt Optimization

Find the best tilt angle:

```
What's the optimal tilt angle for a system in Tokyo?
→ Optimal tilt for Tokyo is approximately 35° (latitude-based)

Compare tilt angles 20°, 30°, and 40° for a 10kW system in Madrid
→ 30° tilt produces 12% more than 20° (optimal for Madrid's latitude)
```

## Tracking Systems

Compare fixed vs tracking:

```
Compare single-axis tracking vs fixed tilt in Phoenix
→ Single-axis tracking produces 25% more energy than fixed tilt

What's the energy gain from tracking in Cape Town?
→ Tracking provides approximately 20% energy gain in Cape Town
```

## System Losses

Analyze losses:

```
What's the clipping loss for a 10kW DC / 8kW AC inverter?
→ Clipping loss is approximately 5% for this DC/AC ratio

How does temperature affect a 10kW system in Dubai?
→ Temperature losses reduce output by ~12% in Dubai's hot climate
```

## Monthly Profiles

See seasonal patterns:

```
Show monthly energy for a 10kW system in London
→ [Shows monthly breakdown with summer peak ~800 kWh, winter low ~200 kWh]

What's the daily energy profile for June in Sydney?
→ Peak production around noon, ~55 kWh/day in June
```

## Tips

**Be specific:**
- ✅ "10kW system in Berlin"
- ❌ "solar panel somewhere"

**Use real locations:**
- ✅ "Tokyo", "Sydney", "Phoenix"
- ❌ "Asia", "near the equator"

**One question at a time:**
- ✅ "What's the annual energy?"
- ❌ "What's the energy and tilt and tracking and losses?"

**Ask follow-ups:**
```
Helio> What's the annual energy for 10kW in Madrid?
→ [Answer]

Helio> What about 15kW?
→ [Helio remembers the location]
```
