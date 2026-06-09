## About AgraBhi 2026-27 (Year 2/3)

Members: Nathan Sharma (team lead), Naitik Patel, Landon Morrison

* **Last year's project video:** [tinyurl.com/agrabhiyear1](https://tinyurl.com/agrabhiyear1)
* **This year's plan video:** [tinyurl.com/agrabhi27plan](https://tinyurl.com/agrabhi27plan)
* **Project Website:** [agrabhi.com](https://agrabhi.com) (temporarily down due to privacy reasons)


#### 1. Drone to Rovers
An important limitation of our project last year was the drone struggled to get through the crop canopy. Its blades could easily damage crops, and designing a solution, such as lowering a pod using a tether while the drone hovers above the crops, would cost significant battery life and be very difficult to build. To fix this, we decided to switch our project to creating a swarm of five rovers. Each rover would cost ~$400, be autonomous, and would communicate with one another to take samples effectively.

#### 2. 3D Mapping
Rather than simply taking a single measurement at points, the rovers will take multiple measurements at different depths per point to calculate a moisture gradient at that location. This allows our models to extend moisture predictions to beneath the soil rather than just being a flat heatmap, which gives farmers significantly more information on their field's moisture patterns.

#### 3. Adaptive Path Planning
We think our rovers can improve their own predictive accuracy by driving to the highest uncertainty areas in its predictions in real time. For example, the system could start with an initial set of moisture measurements across the field, generate a heatmap, then tell each rover to go to the most uncertain point on this heatmap and take a measurement there, repeating the process until accuracy is significantly improved and uncertainty is evenly distributed.
