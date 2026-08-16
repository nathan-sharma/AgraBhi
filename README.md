## About AgraBhi

Nathan Sharma (Founder & Lead) and Landon Morrison (Co-Founder)
<img width="471" height="473" alt="image3 (1)" src="https://github.com/user-attachments/assets/12e93a21-7742-4847-847a-8541341cd4ad" />
<img width="960" height="1096" alt="image1 (1)" src="https://github.com/user-attachments/assets/9aa059a6-3856-4a6b-8b31-df9577a1bdde" />
#### Drone to Rovers

An important limitation of our project last year was that the drone struggled to get through the crop canopy, and its blades could easily damage crops. To fix this, we decided to switch our project to a swarm of rovers. Each rover costs ~$1000, is autonomous, and communicates with one another to take samples effectively.

#### Adaptive Sampling

Our rovers can improve their own predictive accuracy by driving to the most uncertain or unexplored parts of the fields in real time. The swarm starts by randomly taking moisture measurements across the farm field and generates a heatmap. Then, a mother rover receives all data from the other rovers to calculate the most unexplored or uncertain spots each rover should sample.

#### Implementation on Farms

AgraBhi is being implemented in collaboration with the Texas A&M AgriLife Extension and their partner farms. Our moisture data will inform farmers' planting decisions and help the analytical models AgriLife uses to predict crop yield with ground-truth moisture measurements.


<img width="930" height="226" alt="Screenshot 2026-08-15 221113" src="https://github.com/user-attachments/assets/fede8a34-aaa0-4601-b425-8d7352c35577" />

