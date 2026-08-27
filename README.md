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

> **Note:** Without loss of generality, assume Pi 1 arrived at their assigned point before Pi 2. Read the highlighted cells first on every row.

<table>
  <thead>
    <tr>
      <th>Pi 1</th>
      <th>Pi 2</th>
      <th>Laptop (mother)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Current mode: receiving</td>
      <td>Current mode: receiving</td>
      <td>Current mode: receiving</td>
    </tr>
    <tr>
      <td style="background-color:#ffe08a;">
        My current location is very close to my target GPS location I was assigned, so let me extend my soil sensor to the ground, take a reading, and transmit this data with my own special ID so the other rovers know who it came from.<br><br>
        <strong>SWITCHED MODE TO TRANSMITTING</strong>
      </td>
      <td>Oh, I just received some data from Pi 1, I can tell because of the ID on the packet. Since I'm not Mom, I can disregard this, but I know that Pi 1 has already sampled first.</td>
      <td>Okay I just got data from Pi 1. I'll add this to my database and do my calculations once I get data from Pi 2.</td>
    </tr>
    <tr>
      <td style="background-color:#ffe08a;">
        45 seconds later: <strong>SWITCHED MODE TO RECEIVING</strong><br><br>
        Okay now I did my job. All I can do is sit here and wait for a little while until Pi 2 collects their data so Mom can tell me where to go next.
      </td>
      <td>[Pi 2 is driving to their target point]</td>
      <td>[Laptop is waiting]</td>
    </tr>
    <tr>
      <td>Oh I just got some data from Pi 2, but since it's not from Mom because of the ID, I will disregard this.</td>
      <td style="background-color:#ffe08a;">
        Ok I have finally arrived at my target location! I will do the same thing as Pi 1 and transmit my data with my own ID to Mom.<br><br>
        <strong>SWITCHED MODE TO TRANSMITTING</strong>
      </td>
      <td>Okay, I just got data from Pi 2, so I have everything I need for the calculations.</td>
    </tr>
    <tr>
      <td>[Pi 1 is waiting for mother rover's assignment]</td>
      <td>
        45 seconds later: <strong>SWITCHED MODE TO RECEIVING</strong><br><br>
        [Pi 2 is waiting for mother rover's assignment]
      </td>
      <td style="background-color:#ffe08a;">
        Now I'll just calculate the best points for each rover to sample.
      </td>
    </tr>
    <tr>
      <td>Alright, I just got my assignment from the mother rover! Let me start driving there right now.</td>
      <td>Ooh I just got some data! Oh man, but after looking at the ID, I see it's for Pi 1, not for me. So I'm going to continue waiting.</td>
      <td style="background-color:#ffe08a;">
        Here are my calculations: The two most optimal locations are (3,5) and (1,2). Now, I know exactly where Pi 1 and Pi 2 are right now because they sent me their GPS coordinates earlier with an ID. Let me calculate the points closest to each rover so they don't waste their battery unnecessarily. Ok, I think this is the best assignment: Pi 1 should go to (3,5), Pi 2 should go to (1,2).<br><br>
        Let me transmit Pi 1's data first for 45 seconds<br>
        <strong>SWITCHED MODE TO TRANSMITTING</strong>
      </td>
    </tr>
    <tr>
      <td>[Pi 1 is driving to their new target location]</td>
      <td>Alright, I just got my assignment too! Let me start driving there now.</td>
      <td style="background-color:#ffe08a;">
        Now let me transmit Pi 2's data for another 45 seconds before switching back to receiving mode.<br><br>
        After 45 seconds have passed: <strong>SWITCHED MODE TO RECEIVING</strong>.
      </td>
    </tr>
  </tbody>
</table>
