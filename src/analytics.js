const NEW_ENGLAND_STATES = new Set(["CT", "ME", "MA", "NH", "RI", "VT"]);
const LONG_HAUL_THRESHOLD_MILES = 3000;

function normalizeMetric(value, min, max) {
  if (!Number.isFinite(value)) return null;
  if (max === min) return 50;
  return ((value - min) / (max - min)) * 100;
}

function percentChange(current, previous) {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous <= 0) return null;
  return ((current - previous) / previous) * 100;
}

function rankInvestmentCandidates(airports, metrics, limit = 5) {
  const candidates = airports
    .map((airport) => ({ airport, metric: metrics[airport.airportCode] }))
    .filter(({ metric }) => metric && [metric.growthPct, metric.passengerVolume].every(Number.isFinite));

  if (candidates.length === 0) return [];

  const dimensions = ["growthPct", "passengerVolume"];
  const ranges = Object.fromEntries(dimensions.map((key) => {
    const values = candidates.map(({ metric }) => metric[key]);
    return [key, { min: Math.min(...values), max: Math.max(...values) }];
  }));
  const weights = { growthPct: 0.65, passengerVolume: 0.35 };

  return candidates
    .map(({ airport, metric }) => {
      const components = Object.fromEntries(dimensions.map((key) => [
        key,
        normalizeMetric(metric[key], ranges[key].min, ranges[key].max),
      ]));
      const score = dimensions.reduce((total, key) => total + components[key] * weights[key], 0);
      return { airport, metrics: metric, components, score: Number(score.toFixed(1)) };
    })
    .sort((left, right) => right.score - left.score || left.airport.airportCode.localeCompare(right.airport.airportCode))
    .slice(0, limit);
}

function rankNewEnglandAirports(airports, metrics, limit = 5) {
  return rankInvestmentCandidates(
    airports.filter((airport) => NEW_ENGLAND_STATES.has(airport.stateCode)),
    metrics,
    limit,
  );
}

function filterAirports(airports, { stateCodes = [], minimumPassengers = 0 } = {}) {
  const states = new Set(stateCodes.map((state) => state.toUpperCase()));
  return airports.filter((airport) => {
    if (states.size > 0 && !states.has(airport.stateCode)) return false;
    if (airport.serviceLevel === "GA") return false;
    return Number.isFinite(airport.passengerVolume) && airport.passengerVolume >= minimumPassengers;
  });
}

function rankAirports(airports, { metric = "passengerVolume", limit = 10 } = {}) {
  if (!new Set(["passengerVolume", "growthPct"]).has(metric)) {
    throw new Error(`Unsupported airport ranking metric: ${metric}`);
  }
  return airports
    .filter((airport) => Number.isFinite(airport[metric]))
    .toSorted((left, right) => right[metric] - left[metric] || left.airportCode.localeCompare(right.airportCode))
    .slice(0, limit);
}

function compareAirports(airports, codes) {
  const byCode = new Map(airports.map((airport) => [airport.airportCode.toUpperCase(), airport]));
  return codes.map((code) => byCode.get(code.toUpperCase()) ?? null);
}

function compareCongestion(periods, airportCodes) {
  return airportCodes.map((code) => {
    const period = periods[code];
    if (!period || !Number.isFinite(period.operations) || period.operations <= 0) {
      return { airportCode: code, available: false };
    }
    return {
      airportCode: code,
      available: true,
      period: period.period,
      operations: period.operations,
      delayedOperations: period.delayedOperations,
      cancellations: period.cancellations,
      delayRatePct: Number(((period.delayedOperations / period.operations) * 100).toFixed(1)),
      averageDelayMinutes: period.averageDelayMinutes,
    };
  });
}

function haversineMiles(from, to) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const lat1 = radians(from.latitude);
  const lat2 = radians(to.latitude);
  const deltaLat = lat2 - lat1;
  const deltaLon = radians(to.longitude - from.longitude);
  const haversine = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;
  return 3958.8 * 2 * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}

function longHaulShare(segments, airports, thresholdMiles = LONG_HAUL_THRESHOLD_MILES) {
  let totalFlights = 0;
  let longHaulFlights = 0;
  const longHaulRoutes = [];

  for (const segment of segments) {
    const flightCount = Number(segment.flightCount);
    if (!Number.isFinite(flightCount) || flightCount <= 0) continue;
    totalFlights += flightCount;
    const origin = airports[segment.origin];
    const destination = airports[segment.destination];
    if (!origin || !destination) continue;
    const distanceMiles = haversineMiles(origin, destination);
    if (distanceMiles >= thresholdMiles) {
      longHaulFlights += flightCount;
      longHaulRoutes.push({
        origin: segment.origin,
        destination: segment.destination,
        distanceMiles: Math.round(distanceMiles),
        flightCount,
      });
    }
  }

  return {
    available: totalFlights > 0,
    thresholdMiles,
    totalFlights,
    longHaulFlights,
    percentage: totalFlights > 0 ? Number(((longHaulFlights / totalFlights) * 100).toFixed(1)) : null,
    longHaulRoutes,
  };
}

function demandPressure(metrics) {
  const required = [metrics.loadFactorPct, metrics.delayRatePct, metrics.cancellationRatePct];
  if (!required.every(Number.isFinite)) return { available: false, score: null, components: null };

  const components = {
    loadFactor: Math.max(0, Math.min(100, (metrics.loadFactorPct / 95) * 100)),
    delayRate: Math.max(0, Math.min(100, (metrics.delayRatePct / 20) * 100)),
    cancellationRate: Math.max(0, Math.min(100, (metrics.cancellationRatePct / 5) * 100)),
  };
  const score = components.loadFactor * 0.55 + components.delayRate * 0.3 + components.cancellationRate * 0.15;
  return { available: true, score: Number(score.toFixed(1)), components };
}

module.exports = {
  LONG_HAUL_THRESHOLD_MILES,
  compareCongestion,
  compareAirports,
  demandPressure,
  filterAirports,
  haversineMiles,
  longHaulShare,
  percentChange,
  rankAirports,
  rankInvestmentCandidates,
  rankNewEnglandAirports,
};
