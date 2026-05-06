package risk.validation.action.allow.policy_0147

# Auto-generated policy 147 (Rego v1 syntax)
# Package: risk.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0147",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0147_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0147_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0147_allowed if {
    input.user.role == "admin"
}
default policy_0147_allowed = false
