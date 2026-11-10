# Risk level thresholds on the 0-1 risk score
AMBER_THRESHOLD = 0.35
RED_THRESHOLD = 0.65

# Effective rain intensity (mm/h) at which rainfall alone is considered extreme
EXTREME_RAIN_MM_H = 50.0

# Susceptibility weights (must sum to 1.0)
W_DEPRESSION = 0.35   # how far the spot sits below its surroundings
W_CATCHMENT = 0.25    # upstream area draining into the spot
W_DRAIN = 0.20        # distance to nearest stormwater drain
W_HISTORY = 0.20      # past flood reports

# Normalisation caps for each susceptibility input
MAX_DEPTH_M = 6.0
MAX_CATCHMENT_HA = 300.0
MAX_DRAIN_DIST_M = 400.0
MAX_INCIDENTS = 5

# Approximate warning lead when the forecast pushes a spot into a worse level
FORECAST_LEAD_MIN = 45
