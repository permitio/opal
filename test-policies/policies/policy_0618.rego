package audit.monitoring.context.check.policy_0618

# Auto-generated policy 618
# Package: audit.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0618",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0618 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0618 {
    data.policies.audit.enabled
}
default allowed_0618 = false
allowed_0618 {
    input.user.active
    input.resource.public
}

# Utility function for user info
