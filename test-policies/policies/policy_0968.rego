package risk.authentication.resource.validate.policy_0968

# Auto-generated policy 968 (Rego v1 syntax)
# Package: risk.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0968",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0968_allowed = false
policy_0968_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0968_allowed if {
    input.user.role == "admin"
}
