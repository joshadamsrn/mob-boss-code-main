game loop:
the round has phases, rather than time.
PHase 1 is information seeking (who is on your team and who is not)
phase 1 ends when someone dies
phase 2 is a trial
phase 3 is back to phase 1, the new round starts. 

seek information until a murder happens (during interactions), hold a trial, then repeat seek more information until the next murder, etc

Core rule, only 1 person can die at a time, one murder and one trial

police can only kill x mafia. THey can kill half of the mafia rounded down.
(rules and balance like this need to be documented in a weights file)
If the police exceed their limit of how many they are allowed to kill, they lose. The amount left needs to be visible to them as they use them up.

merchant money goals:
The game has a 

jury selection: we still need to figure this out. pick 1/4 random live players, round to odd number.

we'll go over gun tiers later.

app/server roles are as such;
the server holds the state of the game room.
It knows the players and their roles and everything they have and are and what they do. Clients are the players. They can make calls to the api. THey have an html or an app surface from which to display the data so it's easy to see and work with. THe server will present a json definition of the game state. The clients will request this at regular intervals. the game state is dependent on the perspective of the user and their role and identity, right, so there's no leakage.


game play is continuous
apps/client should notify when trial starts
jury need to be notified who they are.
police may kill 1 per round - objective is to elimate all mafia, etc
exclude dead players, but they should see the perspective of the game from someone who is dead (more than when alive)
