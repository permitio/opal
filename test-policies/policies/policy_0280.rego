package risk.authentication.context.verify.policy_0280

# Auto-generated policy 280 (Rego v1 syntax)
# Package: risk.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0280",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0280_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0280_allowed if {
    input.user.role == "admin"
}
policy_0280_allowed if {
    data.policies.risk.enabled
}
