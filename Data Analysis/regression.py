#coded by Nathan
import numpy as np 
import matplotlib.pyplot as plt 
from scipy.optimize import curve_fit
measured_data = np.array([
#Lat, lon, elevation, moisture
    [29.77, -95.68, 30.0, 15.2], [29.77, -95.67, 30.0, 20.5], [29.77, -95.66, 30.0, 25.8],
    [29.76, -95.68, 25.0, 45.1], [29.76, -95.67, 25.0, 50.4], [29.76, -95.66, 25.0, 55.7],
    [29.75, -95.68, 20.0, 80.3], [29.75, -95.67, 20.0, 85.6], [29.75, -95.66, 20.0, 92.1]

])
latitudes = measured_data[:, 0]
longitudes = measured_data[:, 1]
x = measured_data[:, 2] 
y = measured_data[:, 3] 
sumY = sum(y) 
sumX = sum(x) 
num = len(y) 
meanY = sumY/num 
meanX = sumX/num
Sycomp = 0 
Sxcomp = 0
for value in x: 
    Sxcomp += (value - meanX)**2
for value in y: 
    Sycomp += (value - meanY)**2
Sx = ((Sxcomp)/(num - 1))**(1/2)
Sy = ((Sycomp)/(num - 1))**(1/2) 
def calculate_r_squared(y_true, y_predicted): 
    ss_total = ((y_true - np.mean(y_true)) ** 2).sum()
    ss_residual = ((y_true - y_predicted) ** 2).sum()

    if ss_total == 0: 
        return 1.0 if ss_residual == 0 else 0.0 
    r_squared = 1 - (ss_residual)/(ss_total)
    return(r_squared) 
coefficients_linear = np.polyfit(x,y,1) 
y_predicted_linear = np.polyval(coefficients_linear, x) 
r_squared_linear = calculate_r_squared(y, y_predicted_linear)
slope_linear = coefficients_linear[0] 
intercept_linear = coefficients_linear[1] 
r_linear = slope_linear * (Sx/Sy)
print("**Linear**")
print("y = " + str(slope_linear) + "x" + " + " + str(intercept_linear))
print("r^2: " + str(r_squared_linear)) 
linear_model = np.poly1d(coefficients_linear)
coefficients_quadratic = np.polyfit(x,y,2) 
y_predicted_quadratic = np.polyval(coefficients_quadratic, x) 
r_squared_quadratic = calculate_r_squared(y, y_predicted_quadratic)
a_quadratic = coefficients_quadratic[0] 
b_quadratic = coefficients_quadratic[1] 
intercept_quadratic = coefficients_quadratic[2] 
print("      ")
print("*Quadratic**")
print("y = " + str(a_quadratic) + "x^2" + " + " + str(b_quadratic) + "x" + " + " + str(intercept_quadratic))
print("r^2: " + str(r_squared_quadratic))
quadratic_model = np.poly1d(coefficients_quadratic)
coefficients_cubic = np.polyfit(x,y,3)
y_predicted_cubic = np.polyval(coefficients_cubic, x) 
r_squared_cubic = calculate_r_squared(y, y_predicted_cubic) 
a_cubic = coefficients_cubic[0] 
b_cubic = coefficients_cubic[1] 
c_cubic = coefficients_cubic[2] 
intercept_cubic = coefficients_cubic[3]
print("      ")
print("*Cubic**")
print("y = " + str(a_cubic) + "x^3" + " + " + str(b_cubic) + "x^2" + " + " + str(c_cubic) + "x " + " + " + str(intercept_cubic))
print("r^2: " + str(r_squared_cubic))
cubic_model = np.poly1d(coefficients_cubic)
def logarithmic_func(x, a, b):
    return a * np.log(x) + b
popt_log, pcov_log = curve_fit(logarithmic_func, x, y, p0=[1, 1])
a_log, b_log = popt_log
y_pred_log = logarithmic_func(x, a_log, b_log)
r_squared_log = calculate_r_squared(y, y_pred_log)
print("      ")
print("**Logarithmic**")
print(f"y = {a_log:.4f} * ln(x) + {b_log:.4f}")
print("r^2: " + str(r_squared_log))
def exponential_func(x, a, b):
    return a * np.exp(b * x)
popt_exp, pcov_exp = curve_fit(exponential_func, x, y, p0=[1, 0.01])
a_exp, b_exp = popt_exp
y_pred_exp = exponential_func(x, a_exp, b_exp)
r_squared_exp = calculate_r_squared(y, y_pred_exp)
print("      ")
print("**Exponential**")
print(f"y = {a_exp:.4f} * exp({b_exp:.4f} * x)")
print("r^2: " + str(r_squared_exp))
exponential_model = lambda x_val: exponential_func(x_val, a_exp, b_exp)
logarithmic_model_curve_fit = lambda x_val: logarithmic_func(x_val, a_log, b_log)
x_fit = np.linspace(min(x), max(x), 100)
plt.figure(figsize=(10,6))
plt.scatter(x, y, color='red', label='Measured Data')
plt.plot(x_fit, linear_model(x_fit), 
         label = "Linear Fit",
         color ='blue', linestyle='--') 
plt.plot(x_fit, quadratic_model(x_fit), 
         label = "Quadratic Fit", 
         color ='green', linestyle='--')
plt.plot(x_fit, cubic_model(x_fit), 
         label = "Cubic Fit", 
         color ='orange', linestyle='--')  
plt.plot(x_fit, logarithmic_model_curve_fit(x_fit), 
         label = "Logarithmic Fit", 
         color ='black', linestyle='--')
plt.plot(x_fit, exponential_model(x_fit), 
         label = "Exponential Fit", 
         color ='red', linestyle='--')
plt.title('Regression on Measured Drone Data')
plt.xlabel('Elevation (Auxillary Variable)') 
plt.ylabel('Moisture Values')
plt.legend() 
plt.grid(True) 
plt.show()
residuals_linear_list = []
for i in range(len(x)):
    y_actual = y[i]
    y_predicted = linear_model(x[i])
    residual = y_actual - y_predicted
    residuals_linear_list.append(residual)
residuals_linear_array = np.array(residuals_linear_list)
spatial_residuals_linear = np.column_stack((latitudes, longitudes, residuals_linear_array))
residuals_quadratic_list = []
for i in range(len(x)):
    y_actual = y[i]
    y_predicted = quadratic_model(x[i])
    residual = y_actual - y_predicted
    residuals_quadratic_list.append(residual)
residuals_quadratic_array = np.array(residuals_quadratic_list)
spatial_residuals_quadratic = np.column_stack((latitudes, longitudes, residuals_quadratic_array))
residuals_cubic_list = []
for i in range(len(x)):
    y_actual = y[i]
    y_predicted = cubic_model(x[i])
    residual = y_actual - y_predicted
    residuals_cubic_list.append(residual)
residuals_cubic_array = np.array(residuals_cubic_list)
spatial_residuals_cubic = np.column_stack((latitudes, longitudes, residuals_cubic_array))
y_predicted_log = logarithmic_model_curve_fit(x) 
residuals_log = y - y_predicted_log 
spatial_residuals_log = np.column_stack((latitudes, longitudes, residuals_log))
y_predicted_exp = exponential_model(x) 
residuals_exp = y - y_predicted_exp
spatial_residuals_exp = np.column_stack((latitudes, longitudes, residuals_exp))
