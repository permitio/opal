package governance.authorization.user.check.policy_0852

# Auto-generated policy 852 (Rego v1 syntax)
# Package: governance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0852",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0852_allowed if {
    input.user.active
    input.resource.public
}
policy_0852_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0852_allowed if {
    input.user.role == "admin"
}
policy_0852_allowed if {
    data.policies.governance.enabled
}
