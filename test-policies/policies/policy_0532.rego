package risk.monitoring.resource.validate.helpers.policy_0532

# Auto-generated policy 532 (Rego v1 syntax)
# Package: risk.monitoring.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0532",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0532_allowed if {
    input.user.role == "admin"
}
policy_0532_allowed if {
    input.user.active
    input.resource.public
}
policy_0532_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0532_allowed = false
