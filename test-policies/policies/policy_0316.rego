package risk.authentication.resource.check.policy_0316

# Auto-generated policy 316 (Rego v1 syntax)
# Package: risk.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0316",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0316_allowed if {
    data.policies.risk.enabled
}
default policy_0316_allowed = false
policy_0316_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0316_allowed if {
    input.user.active
    input.resource.public
}
