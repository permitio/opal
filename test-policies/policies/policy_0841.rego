package governance.authorization.action.deny.policy_0841

# Auto-generated policy 841 (Rego v1 syntax)
# Package: governance.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0841",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0841_allowed if {
    input.user.role == "admin"
}
policy_0841_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0841_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
