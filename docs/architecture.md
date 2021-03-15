# OPAL Architecture


## Components diagram
<img src="https://i.ibb.co/7W5YwPG/main-numbered.png"  alt="main-numbered" border="0">

- Legend:
    - Blue line- Data flows 
    - Crimson line -Policy flows
- Components numbered in the diagram
    1. OPAL Server
    2. OPAL Client
    3. OPA (Open Policy Agent)
    4. Application services (The application OPAL powers the authorization layer for)
    5. Data service
    6. GIT repository 
    7. Data sources
    8. OPAL admin 
    9. End users


## Flows
The following text describes common data/policy events in an OPAL system.
Note - numbers below reference components in above diagram

- User flows:
    - #### __Authorization queries:__ 
        - Users(9) -> App(4) -> PolicyAgent(3)
        - Users interact with the application triggering authorization queries that the application resolves with the policy agent (directly). The policy agent is constantly kept up-to date by OPAL so it can answer all the queries correctly.

    - #### __Authorization data changes:__ 
        - Users(9) -> App data service(5) -> OPAL-server(1) -> OPAL-client(2) -> PolicyAgent(3)
        - Users (e.g. customers, operators, partners, developers) affect the applications authorization layer (e.g. create new users, assign new roles). Application service triggers an event to OPAL-server, which notifies the clients, which collect the needed data from the affected sources.

- Policy flows
    - #### __Admin updates policy:__ 
        - Admin(8) -> GIT(6) -> OPAL-server(1) -> 



