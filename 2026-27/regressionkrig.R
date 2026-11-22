# =============================================================================
#  Regression kriging of soil moisture on a ridged (mound / furrow) field
#  Row-geometry version
#
#  moisture(s) = b0 + b1 * mound_status(s) + e(s)
#                \______ regression ______/   \__ kriged residual __/
#
#  Covariate: mound_status (1 = mound, 0 = furrow), recorded IN THE FIELD at
#  every sample. Mound status everywhere else comes from the row geometry: one
#  RTK mound centreline (ab_line) plus the row spacing, refined with RTK points
#  on other mound crests (crest_check_csv).
#
#  Outputs: a "moisture if mound" map and a "moisture if furrow" map (5 m),
#  their area-weighted average, and one 10 cm map that switches between them
#  using the row pattern.
#  Packages: sf, gstat, stars, ggplot2
# =============================================================================

#take two rtk gps measurements of the endpoints of the center of my center mound row
#take 5-10 extra rtk gps measurements on the field, with each measurement being taken at the center of any mound row, points should be about doubling distance from the center mound row
#get a csv file of gps coordinates, moisture, and mound status with headers lon,lat,moisture,mound_status
#edit the following settings in the code:
#  input_csv: change to the correct name of my file
#ab_line: the two rtk gps coordinate endpoints of my center mound row, longitude comes first
#row_spacing_m: tape measure estimate of distance between rows
#mound_width_m: measure the closest possible distance between two points on the field I would consider "furrow/non mound points" with a tape measure, should appear perpendicular to the mound row, one side is the last point i would call a furrow, the other side is the first point i would call a furrow
#crest_check_csv: the 5-10 extra rtk gps measurements in a file called crest_check.csv, with headers lon,lat

suppressPackageStartupMessages({
  library(sf)
  library(gstat)
  library(stars)
  library(ggplot2)
})
set.seed(42)

# ---- 0. Settings: edit these ------------------------------------------------
input_csv      <- "soil_moisture_mounds.csv"
lon_col        <- "lon"
lat_col        <- "lat"
value_col      <- "moisture"
cov_col        <- "mound_status"   # 1 = mound, 0 = furrow
value_label    <- "Soil moisture (% VWC)"
valid_range    <- c(0, 100)        # physical limits; c(0, 1) for m3/m3
boundary_file  <- NULL             # optional field boundary (.gpkg/.shp/.kml); leave out headlands
cell_size_m    <- 5                # grid for the smooth, kriged part
dup_tol_m      <- 0.05             # only merge true repeats: a mound and a furrow can be < 1 m apart
nmax_neighbors <- Inf              # Inf = global kriging; 30-100 for > ~1000 samples
out_dir        <- "rk_output"

# Row geometry. RTK coordinates in decimal degrees, longitude first.
ab_line          <- NULL           # rbind(c(lon1, lat1), c(lon2, lat2)): both ends of ONE mound centreline
row_spacing_m    <- 0.76           # mound centre to mound centre (tape estimate; refined by crest_check_csv)
mound_width_m    <- 0.38           # width of the strip classed as mound
crest_check_csv  <- NULL           # recommended: CSV with lon,lat of RTK points on other mound crests
fine_res_m       <- 0.1            # pixel size of the full-resolution map; several pixels per mound

# ---- 1. Read and check -------------------------------------------------------
if (!file.exists(input_csv))
  stop("Can't find '", input_csv, "' in ", getwd(), ". Check the name, or give the full path.")
if (!is.matrix(ab_line) || !all(dim(ab_line) == c(2, 2)))
  stop("Set ab_line to the two RTK end points of one mound centreline: rbind(c(lon1, lat1), c(lon2, lat2))")
if (!is.null(crest_check_csv) && !file.exists(crest_check_csv))
  stop("Can't find '", crest_check_csv, "' in ", getwd(), ".")
dir.create(out_dir, showWarnings = FALSE)

raw  <- read.csv(input_csv)
need <- c(lon_col, lat_col, value_col, cov_col)
if (length(setdiff(need, names(raw)))) stop("Missing column(s): ", paste(setdiff(need, names(raw)), collapse = ", "))
raw <- raw[complete.cases(raw[, need]), ]
if (!all(raw[[cov_col]] %in% c(0, 1))) stop(cov_col, " must be 0 (furrow) or 1 (mound).")
if (any(abs(raw[[lat_col]]) > 90)) stop("Latitude > 90: are lon and lat swapped?")
n_class <- table(factor(raw[[cov_col]], levels = 0:1))
cat(sprintf("Samples: %d furrow, %d mound\n", n_class[["0"]], n_class[["1"]]))
if (any(n_class < 20)) warning("Fewer than ~20 samples of one class: the mound effect will be poorly estimated.")

# ---- 2. Project GPS degrees to metres ---------------------------------------
utm_epsg <- function(lon, lat) {
  zone <- floor((mean(lon) + 180) / 6) + 1
  if (mean(lat) >= 0) 32600 + zone else 32700 + zone
}
crs_utm <- utm_epsg(raw[[lon_col]], raw[[lat_col]])
pts <- st_transform(st_as_sf(raw, coords = c(lon_col, lat_col), crs = 4326), crs_utm)
to_utm_xy <- function(lonlat) st_coordinates(st_transform(st_sfc(st_multipoint(lonlat), crs = 4326), crs_utm))[, 1:2]

# Row geometry in metres
ab_xy <- to_utm_xy(ab_line)
d     <- ab_xy[2, ] - ab_xy[1, ]
nv    <- c(-d[2], d[1]) / sqrt(sum(d^2))                # unit vector perpendicular to the rows
row_bearing <- (atan2(d[1], d[2]) * 180 / pi) %% 180   # clockwise from north, as gstat expects
across_rows <- function(x, y) (x - ab_xy[1, 1]) * nv[1] + (y - ab_xy[1, 2]) * nv[2]   # metres
is_mound <- function(across, spacing, width) {
  off <- ((across + spacing / 2) %% spacing) - spacing / 2   # distance to nearest mound centreline
  (abs(off) <= width / 2) * 1L
}

# ---- 3. Merge repeat readings (same spot AND same mound status) -------------
xy  <- st_coordinates(pts)
key <- paste(round(xy[, 1] / dup_tol_m), round(xy[, 2] / dup_tol_m), pts[[cov_col]])
if (anyDuplicated(key)) {
  means <- tapply(pts[[value_col]], key, mean)
  keep  <- !duplicated(key)
  message(sum(!keep), " repeat reading(s) averaged.")
  pts <- pts[keep, ]
  pts[[value_col]] <- as.numeric(means[key[keep]])
}
n    <- nrow(pts)
f_ok <- as.formula(paste(value_col, "~ 1"))            # ordinary kriging, for comparison
f_rk <- as.formula(paste(value_col, "~", cov_col))     # regression kriging

# ---- 4. Regression step ------------------------------------------------------
ols <- summary(lm(f_rk, data = st_drop_geometry(pts)))
b   <- ols$coefficients
cat(sprintf("\nRegression: furrow mean %.2f | mound effect %+.2f (SE %.2f, p = %.2g) | R2 = %.2f\n",
            b[1, 1], b[2, 1], b[2, 2], b[2, 4], ols$r.squared))
cat("(OLS p-values ignore spatial autocorrelation, so treat them as optimistic.)\n")

# ---- 5. Variograms: raw moisture vs. regression residuals -------------------
# variogram(moisture ~ mound_status) computes the variogram of the residuals.
# Without the covariate, the mound/furrow difference (at < 1 m, far below your
# sample spacing) shows up as a big nugget. With it, the nugget should shrink.
bb     <- st_bbox(pts)
diag_m <- as.numeric(sqrt(diff(bb[c(1, 3)])^2 + diff(bb[c(2, 4)])^2))
cutoff <- diag_m / 2
width  <- cutoff / 15
v_ok <- variogram(f_ok, pts, cutoff = cutoff, width = width)
v_rk <- variogram(f_rk, pts, cutoff = cutoff, width = width)
if (any(v_rk$np < 30)) message("Some lags have < 30 pairs - consider a wider 'width'.")

# ---- 6. Fit variogram models, choose by leave-one-out cross-validation ------
fit_model <- function(v, m) {
  nug0  <- min(v$gamma)
  sill0 <- median(v$gamma[v$dist > max(v$dist) / 2])
  w <- NULL
  fit <- withCallingHandlers(
    tryCatch(fit.variogram(v, vgm(max(sill0 - nug0, sill0 / 2), m, cutoff / 3, nug0),
                           fit.kappa = (m == "Mat")), error = function(e) NULL),
    warning = function(cond) { w <<- conditionMessage(cond); invokeRestart("muffleWarning") })
  ok <- !is.null(fit) && !isTRUE(attr(fit, "singular")) && is.null(w) &&
    all(fit$psill >= 0) && fit$range[2] > 0
  if (ok) fit else NULL
}
practical_range <- function(fit) {
  if (as.character(fit$model[2]) == "Sph") return(fit$range[2])
  vl <- variogramLine(fit, maxdist = 20 * fit$range[2], n = 5000)
  vl$dist[which(vl$gamma - fit$psill[1] >= 0.95 * fit$psill[2])[1]]
}
cv_stats <- function(f, fit) {
  cv <- krige.cv(f, pts, model = fit, nfold = n, nmax = nmax_neighbors, verbose = FALSE)
  list(cv = cv, stats = c(ME = mean(cv$residual), RMSE = sqrt(mean(cv$residual^2)),
                          MSDR = mean(cv$zscore^2), R2 = cor(cv$observed, cv$var1.pred)^2))
}
select_model <- function(v, f, label) {
  fits <- Filter(Negate(is.null), lapply(c(Sph = "Sph", Exp = "Exp", Mat = "Mat"), fit_model, v = v))
  if (!length(fits)) stop("No variogram model converged for ", label)
  cvs <- lapply(fits, cv_stats, f = f)
  tab <- do.call(rbind, lapply(names(fits), function(m) data.frame(
    method = label, model = m, nugget = fits[[m]]$psill[1], partial_sill = fits[[m]]$psill[2],
    practical_range_m = practical_range(fits[[m]]), t(round(cvs[[m]]$stats, 3)))))
  best <- names(fits)[which.min(tab$RMSE)]
  list(fit = fits[[best]], name = best, cv = cvs[[best]]$cv, stats = cvs[[best]]$stats, table = tab)
}
ok <- select_model(v_ok, f_ok, "OK")
rk <- select_model(v_rk, f_rk, "RK")
cat("\nLeave-one-out cross-validation (lower RMSE is better, MSDR ~1 is honest uncertainty):\n")
print(rbind(ok$table, rk$table), row.names = FALSE, digits = 3)
cat(sprintf("\nBest OK: %s, RMSE %.2f | Best RK: %s, RMSE %.2f  ->  %.0f%% lower error with mound_status\n",
            ok$name, ok$stats["RMSE"], rk$name, rk$stats["RMSE"],
            100 * (1 - rk$stats["RMSE"] / ok$stats["RMSE"])))
if (rk$stats["RMSE"] >= ok$stats["RMSE"])
  warning("Regression kriging doesn't beat ordinary kriging: mound_status adds little here.")
write.csv(st_drop_geometry(rk$cv), file.path(out_dir, "cross_validation_rk.csv"), row.names = FALSE)

# ---- 7. Predict "if mound" and "if furrow" everywhere -----------------------
# gstat's krige(moisture ~ mound_status, ...) does regression kriging in one
# step: it estimates b0, b1 by GLS (accounting for spatial correlation), kriges
# the residuals and adds them back, and its variance includes the uncertainty
# of b0 and b1. Prediction is linear in mound_status, so predicting with it set
# to 0 and then 1 gives the furrow and mound surfaces exactly. Both use ALL samples.
if (!is.null(boundary_file)) {
  field <- st_union(st_make_valid(st_transform(st_read(boundary_file, quiet = TRUE), crs_utm)))
} else {
  field <- st_convex_hull(st_union(pts))
}
field_buf <- st_buffer(field, cell_size_m)     # margin so fine-scale resampling has no edge gaps
grid <- st_crop(st_as_stars(st_bbox(field_buf), dx = cell_size_m, dy = cell_size_m), field_buf)
names(grid) <- cov_col

predict_status <- function(status) {
  g <- grid
  g[[1]][!is.na(g[[1]])] <- status
  k <- krige(f_rk, pts, newdata = g, model = rk$fit, nmax = nmax_neighbors, debug.level = 0)
  k$se <- sqrt(k$var1.var)
  k
}
k_f <- predict_status(0)
k_m <- predict_status(1)
mound_effect <- mean(k_m$var1.pred - k_f$var1.pred, na.rm = TRUE)
cat(sprintf("Mound effect used for prediction (GLS): %+.2f\n", mound_effect))

# ---- 8. Mound map from the row geometry --------------------------------------
if (!is.null(crest_check_csv)) {
  # A spacing error adds up row after row: 1 mm off x 400 rows = 40 cm, enough to
  # swap mounds and furrows. Fit the spacing to RTK points on other crests instead.
  chk <- read.csv(crest_check_csv)
  cxy <- st_coordinates(st_transform(st_as_sf(chk, coords = c(lon_col, lat_col), crs = 4326), crs_utm))
  a   <- across_rows(cxy[, 1], cxy[, 2])
  s   <- row_spacing_m
  ord <- order(abs(a))
  for (i in seq_along(ord)) {          # nearest points first, so the row counts stay correct
    use <- ord[seq_len(i)]
    k   <- round(a[use] / s)
    if (any(k != 0)) s <- sum(k * a[use]) / sum(k^2)
  }
  k   <- round(a / s)
  off <- a - k * s
  cat("\nCrest check points (offset = distance from the nearest predicted mound centre):\n")
  print(data.frame(point = seq_along(a), metres_across_rows = round(a, 2), rows_from_AB = k,
                   offset_cm = round(100 * off, 1))[ord, ], row.names = FALSE)
  cat(sprintf("Row spacing: %.4f m entered -> %.4f m fitted\n", row_spacing_m, s))
  if (max(abs(off)) > mound_width_m / 4)
    warning("Some crest points sit > ", round(100 * mound_width_m / 4), " cm off the predicted mound ",
            "centres: the rows aren't one straight, evenly spaced pattern there (a join between ",
            "implement passes, curved rows, or a point not on a crest). Check those points.")
  row_spacing_m <- s
}
fm <- st_as_stars(st_bbox(field), dx = fine_res_m, dy = fine_res_m)
xs <- st_get_dimension_values(fm, "x", center = TRUE)
ys <- st_get_dimension_values(fm, "y", center = TRUE)
fm[[1]] <- is_mound(outer((xs - ab_xy[1, 1]) * nv[1], (ys - ab_xy[1, 2]) * nv[2], "+"),
                    row_spacing_m, mound_width_m)
names(fm) <- cov_col

# Mask to the field by rasterizing it (st_crop on millions of cells runs out of memory)
tm <- fm
tm[[1]][] <- 0
inside <- st_rasterize(st_sf(inside = 1, geometry = field), template = tm)[[1]] == 1
fm[[1]][!inside] <- NA
rm(tm, inside)

# Check the map against what you recorded on the ground. ~90% is the ceiling
# with 10 cm pixels: samples within a few cm of a mound edge are ambiguous.
at_samples <- st_extract(fm, pts)[[1]]
agree <- mean(at_samples == pts[[cov_col]], na.rm = TRUE)
cat(sprintf("Mound map vs. field records at the samples: %.0f%% agree\n", 100 * agree))
if (agree < 0.8)
  warning("Mound map and field records disagree. Check ab_line, the row spacing and the crest points, or: ",
          "if your sample GPS is a phone or handheld (+/- 3 m), it can't resolve rows < 1 m apart, so low ",
          "agreement is expected - then rely on the crest check table instead.")

# 10 cm map = furrow surface where the map says furrow, mound surface where it says mound
warp <- function(s) st_warp(s["var1.pred"], fm, method = "bilinear", use_gdal = TRUE, no_data_value = -9999)
fine_f <- warp(k_f)
fine_m <- warp(k_m)
fine <- fm
names(fine) <- "moisture"
fine[[1]] <- pmin(pmax(ifelse(fm[[1]] == 1, fine_m[[1]], fine_f[[1]]), valid_range[1]), valid_range[2])
mound_area_fraction <- mean(fm[[1]], na.rm = TRUE)

# ---- 9. 5 m outputs ------------------------------------------------------------
clamp <- function(x) pmin(pmax(x, valid_range[1]), valid_range[2])
out <- st_crop(k_f["var1.pred"], field)
names(out) <- "furrow"
out$mound      <- st_crop(k_m["var1.pred"], field)[[1]]
out$cell_avg   <- out$furrow + mound_area_fraction * (out$mound - out$furrow)
out$se_furrow  <- st_crop(k_f["se"], field)[[1]]
out$se_mound   <- st_crop(k_m["se"], field)[[1]]
for (a in c("furrow", "mound", "cell_avg")) out[[a]] <- clamp(out[[a]])

# ---- 10. Plots ---------------------------------------------------------------
ink <- "#1a1a19"; muted <- "#6b6a66"; surface <- "#fcfcfb"
blue <- "#2a78d6"; orange <- "#eb6834"
blue_ramp   <- c("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
orange_ramp <- c("#fde6da", "#f8c0a4", "#f2956d", "#eb6834", "#c94e1f", "#9a3a14", "#6e2a0e")
theme_k <- theme_minimal(base_size = 11) +
  theme(plot.background = element_rect(fill = surface, colour = NA),
        panel.grid = element_line(colour = "#e6e5e1", linewidth = 0.3),
        text = element_text(colour = ink), axis.text = element_text(colour = muted),
        plot.title = element_text(face = "bold"), plot.subtitle = element_text(colour = muted),
        strip.text = element_text(face = "bold", size = 11),
        legend.position = "top", legend.justification = "left")

# 10a. Raw vs residual variogram
lab_ok <- "Moisture (ordinary kriging)"
lab_rk <- "Residual after mound_status (regression kriging)"
vdf <- rbind(data.frame(v_ok[, c("dist", "gamma")], what = lab_ok),
             data.frame(v_rk[, c("dist", "gamma")], what = lab_rk))
ldf <- rbind(data.frame(variogramLine(ok$fit, maxdist = cutoff, n = 200), what = lab_ok),
             data.frame(variogramLine(rk$fit, maxdist = cutoff, n = 200), what = lab_rk))
p_v <- ggplot() +
  geom_line(data = ldf, aes(dist, gamma, colour = what), linewidth = 0.8) +
  geom_point(data = vdf, aes(dist, gamma, colour = what), size = 2.4) +
  scale_colour_manual(values = setNames(c(blue, orange), c(lab_ok, lab_rk)), name = NULL) +
  guides(colour = guide_legend(nrow = 2)) + expand_limits(x = 0, y = 0) +
  labs(title = "Semivariogram before and after the mound/furrow regression",
       subtitle = sprintf("Nugget %.1f -> %.1f: most of the short-range noise was the mound/furrow difference",
                          ok$fit$psill[1], rk$fit$psill[1]),
       x = "Lag distance (m)", y = "Semivariance") + theme_k
ggsave(file.path(out_dir, "variogram_raw_vs_residual.png"), p_v, width = 7.5, height = 5, dpi = 200)

# 10b. Residual variogram along vs across the rows.
# Water moves along furrows, so the residual may be correlated further along rows.
alphas <- c(row_bearing, (row_bearing + 90) %% 180)
dlabs  <- sprintf(c("Along rows (%.0f deg)", "Across rows (%.0f deg)"), alphas)
v_dir <- variogram(f_rk, pts, cutoff = cutoff, width = cutoff / 10, alpha = alphas)
v_dir$direction <- factor(v_dir$dir.hor, alphas, dlabs)
vl_rk <- variogramLine(rk$fit, maxdist = cutoff, n = 200)
p_dir <- ggplot() +
  geom_line(data = vl_rk, aes(dist, gamma, colour = "Isotropic fit"), linewidth = 0.7) +
  geom_point(data = v_dir, aes(dist, gamma, colour = "Directional residual"), size = 2) +
  facet_wrap(~direction, nrow = 1) +
  scale_colour_manual(values = c("Directional residual" = blue, "Isotropic fit" = orange), name = NULL) +
  expand_limits(x = 0, y = 0) +
  labs(title = "Residual variogram along vs. across the rows (anisotropy check)",
       subtitle = "If one direction rises much more slowly, add anisotropy: vgm(..., anis = c(row_bearing, ratio))",
       x = "Lag distance (m)", y = "Semivariance") + theme_k
ggsave(file.path(out_dir, "variogram_directional_residual.png"), p_dir, width = 7.5, height = 3.8, dpi = 200)

# 10c. Mound vs furrow surfaces on one shared scale
lab_f <- "If furrow (mound_status = 0)"
lab_m <- "If mound (mound_status = 1)"
two <- out[c("furrow", "mound")]
names(two) <- c(lab_f, lab_m)
two <- merge(two, name = "surface")              # two attributes -> one "surface" dimension
pts_p <- pts
pts_p$surface <- factor(ifelse(pts[[cov_col]] == 1, lab_m, lab_f), c(lab_f, lab_m))
lon_rng    <- range(st_coordinates(st_transform(field, 4326))[, "X"])
lon_breaks <- pretty(lon_rng, 3)
lon_breaks <- lon_breaks[lon_breaks > lon_rng[1] & lon_breaks < lon_rng[2]]
map_base <- function(layer, ramp, legend_title, samples) {
  suppressMessages(                              # geom_stars/geom_sf bring their own coord; replace it quietly
    ggplot() + layer +
      geom_sf(data = field, fill = NA, colour = muted, linewidth = 0.4) +
      geom_sf(data = samples, shape = 21, size = 1.6, fill = "white", colour = ink, stroke = 0.4) +
      scale_fill_gradientn(colours = ramp, na.value = "transparent", name = legend_title) +
      scale_x_continuous(breaks = lon_breaks) +
      coord_sf(crs = crs_utm, datum = 4326, expand = FALSE) +
      labs(x = NULL, y = NULL) + theme_k + theme(legend.key.width = unit(1.6, "cm")))
}
p_surf <- map_base(geom_stars(data = two), blue_ramp, value_label, pts_p) +
  facet_wrap(~surface) +
  labs(title = "Predicted soil moisture: furrows vs. mounds",
       subtitle = sprintf("Regression kriging, %s residual variogram: the same field pattern, %+.1f on mounds. Dots = samples of that type",
                          rk$name, mound_effect))
ggsave(file.path(out_dir, "moisture_furrow_vs_mound.png"), p_surf, width = 10, height = 5.6, dpi = 200)

p_se <- map_base(geom_stars(data = out["se_furrow"]), orange_ramp, "Std. error", pts) +
  labs(title = "Prediction uncertainty",
       subtitle = "Kriging standard error (furrow surface; the mound surface is nearly identical)")
ggsave(file.path(out_dir, "moisture_se.png"), p_se, width = 7, height = 6, dpi = 200)

# 10d. Full-resolution close-up (15 m x 15 m around the sample nearest the field centre)
ctr <- st_coordinates(st_centroid(field))
pxy <- st_coordinates(pts)
c0  <- pxy[which.min((pxy[, 1] - ctr[1])^2 + (pxy[, 2] - ctr[2])^2), ]
win <- st_bbox(c(xmin = c0[[1]] - 7.5, ymin = c0[[2]] - 7.5, xmax = c0[[1]] + 7.5, ymax = c0[[2]] + 7.5),
               crs = st_crs(crs_utm))
fz      <- fine[win]
pts_win <- pts[st_as_sfc(win), ]
p_zoom <- suppressMessages(ggplot() +
                             geom_stars(data = fz) +
                             geom_sf(data = pts_win, aes(fill = .data[[value_col]]), shape = 21, size = 4, colour = ink, stroke = 0.8) +
                             scale_fill_gradientn(colours = blue_ramp, na.value = "transparent", name = value_label,
                                                  limits = range(c(fz[[1]], pts_win[[value_col]]), na.rm = TRUE)) +
                             coord_sf(crs = crs_utm, expand = FALSE) +
                             labs(title = "Full-resolution prediction (15 m x 15 m window)",
                                  subtitle = sprintf("%g m pixels from the row geometry. Circles = samples, filled with measured value",
                                                     fine_res_m),
                                  x = NULL, y = NULL) + theme_k + theme(legend.key.width = unit(1.6, "cm")))
ggsave(file.path(out_dir, "moisture_fine_zoom.png"), p_zoom, width = 7, height = 7, dpi = 200)

# ---- 11. Export --------------------------------------------------------------
for (a in c("furrow", "mound", "cell_avg", "se_furrow", "se_mound"))
  write_stars(out[a], file.path(out_dir, paste0("moisture_", a, ".tif")))
cells <- st_transform(st_as_sf(out, as_points = TRUE, na.rm = TRUE), 4326)
ll <- st_coordinates(cells)
write.csv(data.frame(lon = round(ll[, 1], 7), lat = round(ll[, 2], 7),
                     round(st_drop_geometry(cells), 3)),
          file.path(out_dir, "moisture_grid.csv"), row.names = FALSE)
write_stars(fine, file.path(out_dir, "moisture_fine.tif"), type = "Float32", options = "COMPRESS=DEFLATE")
write_stars(fm, file.path(out_dir, "mound_status_map.tif"), type = "Byte", NA_value = 255,
            options = "COMPRESS=DEFLATE")   # 255 = outside the field
cat("\nDone. Outputs written to '", out_dir, "/'\n", sep = "")
