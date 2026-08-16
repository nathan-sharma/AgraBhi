## About AgraBhi

Nathan Sharma (Founder & Lead) and Landon Morrison (Co-Founder)
<p float="left">
<img width="466" height="540" alt="Screenshot 2026-08-16 031237" src="https://github.com/user-attachments/assets/4c8137bb-5f67-47d4-8a4b-c40ecf6d1a23" />
<img width="472" height="471" alt="Screenshot 2026-08-16 031248" src="https://github.com/user-attachments/assets/05837d63-da78-4b02-ab14-b36aec3bae19" />
</p>
#### Drone to Rovers

An important limitation of our project last year was that the drone struggled to get through the crop canopy, and its blades could easily damage crops. To fix this, we decided to switch our project to a swarm of rovers. Each rover costs ~$1000, is autonomous, and communicates with one another to take samples effectively.

#### Adaptive Sampling

Our rovers can improve their own predictive accuracy by driving to the most uncertain or unexplored parts of the fields in real time. The swarm starts by randomly taking moisture measurements across the farm field and generates a heatmap. Then, a mother rover receives all data from the other rovers to calculate the most unexplored or uncertain spots each rover should sample.

#### Implementation on Farms

AgraBhi is being implemented in collaboration with the Texas A&M AgriLife Extension and their partner farms. Our moisture data will inform farmers' planting decisions and help the analytical models AgriLife uses to predict crop yield with ground-truth moisture measurements.


<img width="930" height="226" alt="Screenshot 2026-08-15 221113" src="https://github.com/user-attachments/assets/fede8a34-aaa0-4601-b425-8d7352c35577" />

