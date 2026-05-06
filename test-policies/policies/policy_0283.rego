package risk.authentication.resource.verify.policy_0283

# Auto-generated policy 283 (Rego v1 syntax)
# Package: risk.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0283",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0283_allowed if {
    data.policies.risk.enabled
}
policy_0283_allowed if {
    input.user.role == "admin"
}
policy_0283_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0283_allowed if {
    input.user.active
    input.resource.public
}
