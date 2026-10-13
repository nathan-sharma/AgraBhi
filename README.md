## About AgraBhi

Founded by Nathan Sharma (lead) and Landon Morrison (co-founder)

<img width="905" height="414" alt="Screenshot 2026-08-16 031706" src="https://github.com/user-attachments/assets/66413854-d41f-47a1-8814-22abac481eb5" />

#### Drone to Rovers
An important limitation of our project last year was that the drone struggled to get through the crop canopy, and its blades could easily damage crops. To address this issue, we decided to switch our project to a swarm of rovers. Each rover costs ~$1500, supports two modes (pre-planting and in-season), and navigates the field autonomously.

#### Modular Design

<img width="117.2" height="162.4" alt="tower" src="https://github.com/user-attachments/assets/bf4a8757-ff48-4ad2-8ab6-56f918e75e69" />

Pre-planting: Rovers use penetration towers and sensor probes to adaptively sample soil moisture and temperature.

<img width="120.6" height="138.8" alt="armcam" src="https://github.com/user-attachments/assets/6f2c46f2-0843-43f2-86cb-a99e45a1e590" />

In-Season: Robotic arms with 360-degree cameras are mounted on the rovers. As they drive through the field, they capture and stitch high-definition panoramic images, then feed them to our YOLO model to detect disease and count cotton bolls.

Rovers can easily switch between the pre-planting and in-season modes by swapping their top assemblies.

#### Implementation on Farms
AgraBhi is being implemented in collaboration with the Texas A&M AgriLife Extension. Our soil moisture data help local farmers make better-informed planting decisions, and our cotton boll data provide AgriLife’s models with growth indicators, helping them better predict yield on their partner farms.


<img width="930" height="226" alt="Screenshot 2026-08-15 221113" src="https://github.com/user-attachments/assets/fede8a34-aaa0-4601-b425-8d7352c35577" />

