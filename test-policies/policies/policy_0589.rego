package governance.enforcement.resource.validate.policy_0589

# Auto-generated policy 589 (Rego v1 syntax)
# Package: governance.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0589",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0589_allowed if {
    input.user.role == "admin"
}
policy_0589_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
