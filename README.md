## About AgraBhi

Founded by Nathan Sharma (lead) and Landon Morrison


<img width="905" height="414" alt="Screenshot 2026-08-16 031706" src="https://github.com/user-attachments/assets/66413854-d41f-47a1-8814-22abac481eb5" />

#### Drone to Rovers
An important limitation of our project last year was that the drone struggled to get through the crop canopy, and its blades could easily damage crops. To fix this, we decided to switch our project to a swarm of rovers. Each rover costs ~$1500, is autonomous, and adaptively samples the field.

#### Adaptive Sampling
Our rovers can improve their own predictive accuracy by driving to the most uncertain or unexplored parts of the fields in real time. The swarm starts by taking evenly distributed moisture measurements across the farm field and generates a heatmap. Then, our app receives all data from the other rovers to calculate the most unexplored or uncertain spots each of them should sample, transmitting assignments over LoRa radio.

#### Implementation on Farms
AgraBhi is being implemented in collaboration with the Texas A&M AgriLife Extension and their partner farms. Our soil moisture data will help farmers' planting decisions, and our visual crop data with ArmCam (more on this soon) will help the analytical models AgriLife uses to predict crop yield by providing cotton boll counts.


<img width="930" height="226" alt="Screenshot 2026-08-15 221113" src="https://github.com/user-attachments/assets/fede8a34-aaa0-4601-b425-8d7352c35577" />

