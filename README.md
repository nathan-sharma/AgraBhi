This project won in the **Senior Division** of the **Environmental Engineering** category at two science fairs:

* 🥈 **2nd Place** at the 2026 Science and Engineering Fair of Houston
* 🥉 **3rd Place** at the 2026 Texas Science and Engineering Fair (**State Finalist**)

> [!IMPORTANT]
> We are working toward ISEF qualification with our 2027 extension project (coming soon!)

---

## About AgraBhi 2025-26 (Year 1/3)
### 📷 Project video 
### https://tinyurl.com/agrabhiyear1 

Variation in soil moisture across agricultural fields reduces crop yields and leads to inefficient water management. Climate change has increased the variability of soil moisture, intensifying this problem. Existing soil moisture gauging methods fail to capture moisture at the root level of crops.

An autonomous drone system, built for under $1000, collects soil moisture data and generates high-resolution field maps using various interpolation models and environmental covariates (i.e., elevation & irrigation proximity data). The drone uses:

* A custom linear actuator-driven soil sensor probe, extending the sensor 11 centimeters into the ground.
* A Real-Time Kinematic (RTK) GPS, a positioning system that provides centimeter-level accuracy using corrections from a fixed base station.
* Raspberry Pi / Pixhawk communication for hands-free data collection upon landing.

The drone can be controlled completely hands-free via a custom-coded application named the AgraBhi Data Hub, accessible on any web browser with a stable internet connection. Custom-written code collected data at landing points, controlled the actuator, and evaluated interpolation methods.

Regarding data analysis, among Ordinary Kriging, Regression Kriging, and Inverse Distance Weighted Interpolation, Regression Kriging demonstrated the smallest Root-Mean-Square Error (RMSE) in Leave-One-Out-Cross-Validation (LOOCV) and reasonable Mean Error (ME) when coupled with elevation data. Field validation shows interpolated moisture values are within experimental uncertainty of ground-truth measurements. While commercial agricultural drones cost several thousand dollars, our relatively low-cost system provides high-resolution, spatially explicit moisture mapping, revealing detailed patterns of soil moisture variation and potentially supporting improved irrigation decision-making and water efficiency.
