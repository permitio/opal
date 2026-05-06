package governance.validation.policy.deny.policy_0946

# Auto-generated policy 946 (Rego v1 syntax)
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0946",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0946_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0946_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0946_allowed if {
    input.user.role == "admin"
}
default policy_0946_allowed = false
