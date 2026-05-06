package compliance.enforcement.user.validate.core.policy_0510

# Auto-generated policy 510 (Rego v1 syntax)
# Package: compliance.enforcement.user.validate.core

# Metadata
metadata := {
    "policy_id": "0510",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0510_allowed if {
    input.user.role == "admin"
}
policy_0510_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0510_allowed if {
    input.user.active
    input.resource.public
}
