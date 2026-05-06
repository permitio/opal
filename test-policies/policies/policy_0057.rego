package risk.monitoring.policy.validate.policy_0057

# Auto-generated policy 57 (Rego v1 syntax)
# Package: risk.monitoring.policy.validate

# Metadata
metadata := {
    "policy_id": "0057",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0057_allowed if {
    input.user.role == "admin"
}
default policy_0057_allowed = false
policy_0057_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
