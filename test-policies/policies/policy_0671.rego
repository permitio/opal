package compliance.monitoring.action.deny.logic.policy_0671

# Auto-generated policy 671 (Rego v1 syntax)
# Package: compliance.monitoring.action.deny.logic

# Metadata
metadata := {
    "policy_id": "0671",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0671_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0671_allowed = false
policy_0671_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
