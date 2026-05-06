package access.validation.user.verify.policy_0134

# Auto-generated policy 134 (Rego v1 syntax)
# Package: access.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0134",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0134_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0134_allowed = false
policy_0134_allowed if {
    input.user.role == "admin"
}
