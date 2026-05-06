package governance.validation.resource.check.helpers.policy_0666

# Auto-generated policy 666 (Rego v1 syntax)
# Package: governance.validation.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0666",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0666_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0666_allowed if {
    input.user.active
    input.resource.public
}
policy_0666_allowed if {
    input.user.role == "admin"
}
