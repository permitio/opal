package risk.authentication.policy.verify.policy_0737

# Auto-generated policy 737 (Rego v1 syntax)
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0737",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0737_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0737_allowed = false
