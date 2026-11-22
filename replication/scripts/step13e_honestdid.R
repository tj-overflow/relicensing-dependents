# Step 13e: Rambachan-Roth sensitivity with HonestDiD.
# Inputs: outputs/step13/hd_{event}_{outcome}_beta.csv and _sigma.csv (step13d_export_es.py).
# Order: pre-period coefficients (reference quarter omitted), then the event quarter and the post quarters.
# Targets, as fixed in step13b_honest.py before the bounds were seen:
#   avg_post   = mean over post quarters after the event quarter (event quarter weight 0)
#   first_year = mean over the first four post quarters after the event quarter
# Restrictions:
#   relative magnitudes (DeltaRM), Mbar in {0, 0.1, 0.25, 0.5, 1, 1.5, 2}; default method (C-LF)
#   smoothness (DeltaSD), M in {0, 0.005, 0.01, 0.02, 0.03, 0.05}; default method (FLCI)
# Breakdown: the smallest grid value at which the robust 95% CI includes zero (RM grid step 0.05 up to 2;
# SD grid step 0.0025 up to 0.05).
# Output: outputs/step13/honestdid.csv, honestdid_breakdown.csv
suppressPackageStartupMessages(library(HonestDiD))
args <- commandArgs(trailingOnly = FALSE)
here <- dirname(normalizePath(sub("--file=", "", args[grep("--file=", args)])))
O <- file.path(dirname(here), "outputs", "step13")
rows <- list(); brk <- list()
for (ev in c("akka", "es")) for (m in c("M1", "M1s")) {
  b <- read.csv(file.path(O, sprintf("hd_%s_%s_beta.csv", ev, m)))
  S <- as.matrix(read.csv(file.path(O, sprintf("hd_%s_%s_sigma.csv", ev, m)), header = FALSE))
  npre <- sum(b$period == "pre"); npost <- nrow(b) - npre
  L <- list(avg_post = c(0, rep(1 / (npost - 1), npost - 1)),
            first_year = c(0, rep(0.25, 4), rep(0, npost - 5)))
  for (tn in names(L)) {
    l <- matrix(L[[tn]], ncol = 1)
    orig <- constructOriginalCS(betahat = b$beta, sigma = S, numPrePeriods = npre, numPostPeriods = npost, l_vec = l)
    rows[[length(rows) + 1]] <- data.frame(event = ev, outcome = m, target = tn, restriction = "parallel_trends",
                                           M = NA, lb = orig$lb, ub = orig$ub)
    rm <- createSensitivityResults_relativeMagnitudes(betahat = b$beta, sigma = S, numPrePeriods = npre,
            numPostPeriods = npost, Mbarvec = c(0, 0.1, 0.25, 0.5, 1, 1.5, 2), l_vec = l)
    rows[[length(rows) + 1]] <- data.frame(event = ev, outcome = m, target = tn, restriction = "RM",
                                           M = rm$Mbar, lb = rm$lb, ub = rm$ub)
    sd <- createSensitivityResults(betahat = b$beta, sigma = S, numPrePeriods = npre, numPostPeriods = npost,
            Mvec = c(0, 0.005, 0.01, 0.02, 0.03, 0.05), l_vec = l)
    rows[[length(rows) + 1]] <- data.frame(event = ev, outcome = m, target = tn, restriction = "SD",
                                           M = sd$M, lb = sd$lb, ub = sd$ub)
    # breakdowns
    g <- seq(0, 2, 0.05)
    rmg <- createSensitivityResults_relativeMagnitudes(betahat = b$beta, sigma = S, numPrePeriods = npre,
             numPostPeriods = npost, Mbarvec = g, l_vec = l)
    hit <- rmg$Mbar[rmg$lb <= 0 & rmg$ub >= 0]
    sdg <- createSensitivityResults(betahat = b$beta, sigma = S, numPrePeriods = npre, numPostPeriods = npost,
             Mvec = seq(0, 0.05, 0.0025), l_vec = l)
    hs <- sdg$M[sdg$lb <= 0 & sdg$ub >= 0]
    brk[[length(brk) + 1]] <- data.frame(event = ev, outcome = m, target = tn,
                                         theta = sum(l * b$beta[(npre + 1):(npre + npost)]),
                                         breakdown_RM = if (length(hit)) min(hit) else NA,
                                         breakdown_SD = if (length(hs)) min(hs) else NA)
    cat(ev, m, tn, "done\n")
  }
}
R <- do.call(rbind, rows); B <- do.call(rbind, brk)
write.csv(R, file.path(O, "honestdid.csv"), row.names = FALSE)
write.csv(B, file.path(O, "honestdid_breakdown.csv"), row.names = FALSE)
print(B)
