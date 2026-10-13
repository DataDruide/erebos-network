---- MODULE erebos_governance ----
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS 
    Peers,
    Proposals,
    QuorumSize,
    MaxTime

ASSUME 
    /\ QuorumSize \in Nat
    /\ QuorumSize > 0
    /\ MaxTime \in Nat
    /\ MaxTime > 0

VARIABLES
    proposalState,
    votes,
    execTime,
    currentTime,
    budget

vars == <<proposalState, votes, execTime, currentTime, budget>>

TypeOK ==
    /\ proposalState \in [Proposals -> {"pending","passed","failed","executed"}]
    /\ votes \in [Proposals -> SUBSET Peers]
    /\ execTime \in [Proposals -> Nat]
    /\ currentTime \in 0..MaxTime
    /\ budget \in [cap : Nat, committed : Nat, spent : Nat]

BudgetInv ==
    /\ budget.cap >= budget.committed
    /\ budget.committed >= budget.spent
    /\ budget.spent >= 0

QuorumSafety ==
    \A p \in Proposals :
        proposalState[p] = "executed" => Cardinality(votes[p]) >= QuorumSize

TimelockSafety ==
    \A p \in Proposals :
        proposalState[p] = "executed" => 
            /\ execTime[p] > 0
            /\ currentTime >= execTime[p]

Init ==
    /\ proposalState = [p \in Proposals |-> "pending"]
    /\ votes = [p \in Proposals |-> {}]
    /\ execTime = [p \in Proposals |-> 0]
    /\ currentTime = 0
    /\ budget = [cap |-> 1000, committed |-> 0, spent |-> 0]

Vote(p) ==
    /\ proposalState[p] = "pending"
    /\ \E peer \in Peers : peer \notin votes[p]
    /\ votes' = [votes EXCEPT ![p] = votes[p] \cup {CHOOSE peer \in Peers : peer \notin votes[p]}]
    /\ UNCHANGED <<proposalState, execTime, currentTime, budget>>

Pass(p) ==
    /\ proposalState[p] = "pending"
    /\ Cardinality(votes[p]) >= QuorumSize
    /\ proposalState' = [proposalState EXCEPT ![p] = "passed"]
    /\ execTime' = [execTime EXCEPT ![p] = currentTime + 10]
    /\ UNCHANGED <<votes, currentTime, budget>>

Fail(p) ==
    /\ proposalState[p] = "pending"
    /\ Cardinality(votes[p]) < QuorumSize
    /\ currentTime >= MaxTime
    /\ proposalState' = [proposalState EXCEPT ![p] = "failed"]
    /\ UNCHANGED <<votes, execTime, currentTime, budget>>

Tick ==
    /\ currentTime < MaxTime
    /\ currentTime' = currentTime + 1
    /\ UNCHANGED <<proposalState, votes, execTime, budget>>

Execute(p) ==
    /\ proposalState[p] = "passed"
    /\ currentTime >= execTime[p]
    /\ budget.committed + 10 <= budget.cap
    /\ proposalState' = [proposalState EXCEPT ![p] = "executed"]
    /\ budget' = [budget EXCEPT !.committed = budget.committed + 10, !.spent = budget.spent + 10]
    /\ UNCHANGED <<votes, execTime, currentTime>>

Next ==
    \/ \E p \in Proposals : Vote(p)
    \/ \E p \in Proposals : Pass(p)
    \/ \E p \in Proposals : Fail(p)
    \/ \E p \in Proposals : Execute(p)
    \/ Tick

Spec == Init /\ [][Next]_vars

Safety ==
    /\ TypeOK
    /\ BudgetInv
    /\ QuorumSafety
    /\ TimelockSafety

====
