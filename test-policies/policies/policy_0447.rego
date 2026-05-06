package risk.authentication.resource.check.policy_0447

# Auto-generated policy 447 (Rego v1 syntax)
# Package: risk.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0447",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0447_allowed if {
    input.user.role == "admin"
}
policy_0447_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
