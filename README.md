## About AgraBhi

Nathan Sharma (Founder & Lead) and Landon Morrison (Co-Founder)


<img width="905" height="414" alt="Screenshot 2026-08-16 031706" src="https://github.com/user-attachments/assets/66413854-d41f-47a1-8814-22abac481eb5" />

#### Drone to Rovers

An important limitation of our project last year was that the drone struggled to get through the crop canopy, and its blades could easily damage crops. To fix this, we decided to switch our project to a swarm of rovers; each rover costs ~$1000, is autonomous, and communicates with one another to take samples effectively.

#### Adaptive Sampling

Our rovers can improve their own predictive accuracy by driving to the most uncertain or unexplored parts of the fields in real time. The swarm starts by randomly taking moisture measurements across the farm field and generates a heatmap. Then, a mother rover receives all data from the other rovers to calculate the most unexplored or uncertain spots each rover should sample.

#### Implementation on Farms

AgraBhi is being implemented in collaboration with the Texas A&M AgriLife Extension and their partner farms. Our moisture data will inform farmers' planting decisions and help the analytical models AgriLife uses to predict crop yield with ground-truth moisture measurements.


<img width="930" height="226" alt="Screenshot 2026-08-15 221113" src="https://github.com/user-attachments/assets/fede8a34-aaa0-4601-b425-8d7352c35577" />


## Radio Communication between rovers explained

> **Note:** Without loss of generality, assume Pi 1 arrived at their assigned point before Pi 2. Read the cells with yellow squares first on every row to avoid confusion!

| Pi 1 | Pi 2 | Laptop (mother) |
|---|---|---|
| Current mode: receiving | Current mode: receiving | Current mode: receiving |
| 🟨 My current location is very close to my target GPS location I was assigned, so let me extend my soil sensor to the ground, take a reading, and transmit this data with my own special ID so the other rovers know who it came from.<br><br>**SWITCHED MODE TO TRANSMITTING** | Oh, I just received some data from Pi 1, I can tell because of the ID on the packet. Since I'm not Mom, I can disregard this, but I know that Pi 1 has already sampled first. | Okay I just got data from Pi 1. I'll add this to my database and do my calculations once I get data from Pi 2. |
| 🟨 45 seconds later: **SWITCHED MODE TO RECEIVING**<br><br>Okay now I did my job. All I can do is sit here and wait for a little while until Pi 2 collects their data so Mom can tell me where to go next. | [Pi 2 is driving to their target point] | [Laptop is waiting] |
| Oh I just got some data from Pi 2, but since it's not from Mom because of the ID, I will disregard this. | 🟨 Ok I have finally arrived at my target location! I will do the same thing as Pi 1 and transmit my data with my own ID to Mom.<br><br>**SWITCHED MODE TO TRANSMITTING** | Okay, I just got data from Pi 2, so I have everything I need for the calculations. |
| [Pi 1 is waiting for mother rover's assignment] | 45 seconds later: **SWITCHED MODE TO RECEIVING**<br><br>[Pi 2 is waiting for mother rover's assignment] | 🟨 Now I'll just calculate the best points for each rover to sample. |
| Alright, I just got my assignment from the mother rover! Let me start driving there right now. | Ooh I just got some data! Oh man, but after looking at the ID, I see it's for Pi 1, not for me. So I'm going to continue waiting. | 🟨 Here are my calculations: The two most optimal locations are (a,b) and (x,y). Now, I know exactly where Pi 1 and Pi 2 are right now because they sent me their GPS coordinates earlier with an ID. Let me calculate the points closest to each rover so they don't waste their battery unnecessarily. Ok, I think this is the best assignment: Pi 1 should go to (a,b), Pi 2 should go to (x,y).<br><br>Let me transmit Pi 1's data first for 45 seconds<br>**SWITCHED MODE TO TRANSMITTING** |
| [Pi 1 is driving to their new target location] | Alright, I just got my assignment too! Let me start driving there now. | 🟨 Now let me transmit Pi 2's data for another 45 seconds before switching back to receiving mode.<br><br>After 45 seconds have passed: **SWITCHED MODE TO RECEIVING**. |
