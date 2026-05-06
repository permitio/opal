package risk.authentication.policy.verify.policy_0409

# Auto-generated policy 409 (Rego v1 syntax)
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0409",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0409_allowed if {
    input.user.role == "admin"
}
policy_0409_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0409_allowed = false
